# -*- coding: utf-8 -*-
"""MiniLLM：最小的中文生成式模型（decoder-only GPT），涵盖数据、预训练、使用三步。

用法（在项目根目录）:
  # 1. 预训练：--data 传任意 utf-8 中文 txt（如盘龙小说全文）
  .venv/bin/python chapter3/minillm.py train --data chapter3/data/sample_ch3.md --steps 2000
  # 2. 使用：加载 checkpoint 续写
  .venv/bin/python chapter3/minillm.py generate --prompt "智能体是"

设计取舍（刻意保持最小）:
  - 字符级分词：中文无需分词器训练，一个字一个 token，损失略高但零依赖
  - 随机裁剪取 batch：不做 DataLoader/Epoch，几十行搞定等价效果
  - 因果掩码用 register_buffer 常量：每步不重复构造
"""
import argparse
import os

import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------- 超参数（模型约 0.8M 参数，CPU 几分钟可训练） ----------------
BLOCK_SIZE = 128   # 上下文长度：模型一次能看的字符数
D_MODEL = 128      # 隐藏维度
N_LAYER = 4        # Transformer 层数
N_HEAD = 4         # 注意力头数
DROPOUT = 0.1
BATCH_SIZE = 32
LR = 3e-4

CKPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkpoints")


# ---------------- 第一步：数据（字符级分词 + batch 采样） ----------------

class CharTokenizer:
    """字符级分词器：vocab = 语料中出现过的所有字符。

    stoi/itoby 为 字符->id / id->字符 的映射表。
    """

    def __init__(self, text: str):
        chars = sorted(set(text))
        self.stoi = {ch: i for i, ch in enumerate(chars)}
        self.itos = {i: ch for i, ch in enumerate(chars)}

    def encode(self, text: str) -> list[int]:
        # 未登录字符统一映射为 0（第一个字符），保证 encode 不抛异常
        return [self.stoi.get(ch, 0) for ch in text]

    def decode(self, ids: list[int]) -> str:
        return "".join(self.itos[i] for i in ids)

    @property
    def vocab_size(self) -> int:
        return len(self.stoi)


def get_batch(ids: torch.Tensor):
    """随机裁剪出一批 (x, y)：x 是长度 BLOCK_SIZE 的片段，y 是后移一位的标签。"""
    ix = torch.randint(len(ids) - BLOCK_SIZE - 1, (BATCH_SIZE,))
    x = torch.stack([ids[i:i + BLOCK_SIZE] for i in ix])
    y = torch.stack([ids[i + 1:i + 1 + BLOCK_SIZE] for i in ix])
    return x, y


# ---------------- 第二步：模型（迷你 GPT，decoder-only） ----------------

class CausalSelfAttention(nn.Module):
    """带因果掩码的多头自注意力：每个位置只能看到自己和之前的位置。"""

    def __init__(self, d_model: int, n_head: int):
        super().__init__()
        assert d_model % n_head == 0
        self.n_head = n_head
        self.d_k = d_model // n_head
        # Q/K/V 合并为一个投影，输出一个投影
        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.proj = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(DROPOUT)
        # 因果掩码常量：mask[i][j]=0 表示 j>i（未来位置）不可见
        mask = torch.tril(torch.ones(BLOCK_SIZE, BLOCK_SIZE)).bool()
        self.register_buffer("mask", mask)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        # 拆头：(B, T, C) -> (B, n_head, T, d_k)
        q = q.view(B, T, self.n_head, self.d_k).transpose(1, 2)
        k = k.view(B, T, self.n_head, self.d_k).transpose(1, 2)
        v = v.view(B, T, self.n_head, self.d_k).transpose(1, 2)

        attn = (q @ k.transpose(-2, -1)) / (self.d_k ** 0.5)
        attn = attn.masked_fill(~self.mask[:T, :T], float("-inf"))  # 遮住未来
        attn = F.softmax(attn, dim=-1)
        attn = self.dropout(attn)

        out = (attn @ v).transpose(1, 2).contiguous().view(B, T, C)
        return self.proj(out)


class Block(nn.Module):
    """一层 Transformer：Pre-LN 结构（先归一化再进子层，训练更稳）。"""

    def __init__(self, d_model: int, n_head: int):
        super().__init__()
        self.ln1 = nn.LayerNorm(d_model)
        self.attn = CausalSelfAttention(d_model, n_head)
        self.ln2 = nn.LayerNorm(d_model)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, 4 * d_model),
            nn.GELU(),
            nn.Linear(4 * d_model, d_model),
            nn.Dropout(DROPOUT),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.ln1(x))   # 残差 + 自注意力
        x = x + self.ffn(self.ln2(x))    # 残差 + 前馈网络
        return x


class MiniGPT(nn.Module):
    """最小的 decoder-only 生成模型：嵌入 -> N 层 Block -> 归一化 -> 输出头。"""

    def __init__(self, vocab_size: int):
        super().__init__()
        self.tok_emb = nn.Embedding(vocab_size, D_MODEL)
        self.pos_emb = nn.Embedding(BLOCK_SIZE, D_MODEL)
        self.blocks = nn.ModuleList([Block(D_MODEL, N_HEAD) for _ in range(N_LAYER)])
        self.ln_f = nn.LayerNorm(D_MODEL)
        self.head = nn.Linear(D_MODEL, vocab_size)

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        B, T = idx.shape
        pos = torch.arange(T, device=idx.device)
        x = self.tok_emb(idx) + self.pos_emb(pos)
        for block in self.blocks:
            x = block(x)
        return self.head(self.ln_f(x))  # logits: (B, T, vocab_size)

    def generate(self, idx: torch.Tensor, max_new_tokens: int,
                 temperature: float = 0.8, top_k: int = 20) -> torch.Tensor:
        """自回归生成：每步取最后一个位置的 logits，按温度采样出下一个字符。"""
        self.eval()
        for _ in range(max_new_tokens):
            idx_cond = idx[:, -BLOCK_SIZE:]           # 上下文超长时截断
            logits = self(idx_cond)[:, -1] / temperature
            if top_k:
                # 只在概率最高的 top_k 个字符里采样，避免纯随机噪声
                kth = logits.topk(top_k, dim=-1).values[:, -1:]
                logits = logits.masked_fill(logits < kth, float("-inf"))
            probs = F.softmax(logits, dim=-1)
            next_id = torch.multinomial(probs, 1)
            idx = torch.cat([idx, next_id], dim=1)
        return idx


# ---------------- 预训练与使用入口 ----------------

def train(data_path: str, steps: int, ckpt_name: str = "minillm.pt",
          d_model: int | None = None, n_layer: int | None = None, n_head: int | None = None):
    """预训练主流程：加载数据 -> 逐 batch 预测下一个字符 -> 定期评估并存档。

    d_model/n_layer/n_head 可选覆盖模块级默认超参（须在构建模型前设置）。
    """
    global D_MODEL, N_LAYER, N_HEAD
    if d_model:
        D_MODEL = d_model
    if n_layer:
        N_LAYER = n_layer
    if n_head:
        N_HEAD = n_head
    torch.manual_seed(0)
    device = "cpu"

    with open(data_path, encoding="utf-8") as f:
        text = f.read()
    tokenizer = CharTokenizer(text)
    ids = torch.tensor(tokenizer.encode(text), dtype=torch.long)
    split = int(len(ids) * 0.95)
    train_ids, val_ids = ids[:split], ids[split:]
    print(f"语料 {len(text)} 字，词表 {tokenizer.vocab_size}，训练 {len(train_ids)} / 验证 {len(val_ids)}")

    model = MiniGPT(tokenizer.vocab_size).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"模型参数量: {n_params / 1e6:.2f}M")
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)

    def eval_loss(ids):
        """采 10 个 batch 估算指定语料的平均损失。"""
        model.eval()
        with torch.no_grad():
            loss = sum(F.cross_entropy(model(x).reshape(-1, model.head.out_features), y.reshape(-1))
                       for x, y in (get_batch(ids) for _ in range(10))) / 10
        model.train()
        return loss.item()

    for step in range(1, steps + 1):
        x, y = get_batch(train_ids)
        logits = model(x)
        loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), y.reshape(-1))
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if step % 200 == 0 or step == steps:
            print(f"step {step:5d} | train loss {loss.item():.3f} | val loss {eval_loss(val_ids):.3f}")

    os.makedirs(CKPT_DIR, exist_ok=True)
    ckpt_path = os.path.join(CKPT_DIR, ckpt_name)
    # 结构和权重一起存：generate 时按同样的超参重建模型，避免尺寸不匹配
    torch.save({"model": model.state_dict(), "vocab": tokenizer.stoi,
                "config": {"d_model": D_MODEL, "n_layer": N_LAYER,
                           "n_head": N_HEAD, "block_size": BLOCK_SIZE}}, ckpt_path)
    print(f"checkpoint 已保存: {ckpt_path}")


def generate(prompt: str, max_new_tokens: int, ckpt_name: str = "minillm.pt",
             temperature: float = 0.8, top_k: int = 20) -> str:
    """使用：加载 checkpoint，对 prompt 续写。"""
    ckpt_path = os.path.join(CKPT_DIR, ckpt_name)
    ckpt = torch.load(ckpt_path, weights_only=True)
    tokenizer = CharTokenizer("")
    tokenizer.stoi = ckpt["vocab"]
    tokenizer.itos = {i: ch for ch, i in ckpt["vocab"].items()}

    # 从 checkpoint 恢复模型结构；旧版 checkpoint 无 config 时用代码默认值
    global D_MODEL, N_LAYER, N_HEAD
    config = ckpt.get("config")
    if config:
        D_MODEL = config["d_model"]
        N_LAYER = config["n_layer"]
        N_HEAD = config["n_head"]
    print(f"加载模型: d_model={D_MODEL}, {N_LAYER} 层, {N_HEAD} 头")
    model = MiniGPT(len(tokenizer.stoi))
    model.load_state_dict(ckpt["model"])
    idx = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long)
    out = model.generate(idx, max_new_tokens, temperature=temperature, top_k=top_k)
    return tokenizer.decode(out[0].tolist())


def chat(ckpt_name: str = "minillm.pt", max_new_tokens: int = 200):
    """交互测试模式：终端里连续输入 prompt，回车生成，Ctrl+C/空行退出。"""
    print(f"交互模式（模型: {ckpt_name}）。输入起始文字回车生成，直接回车退出。")
    while True:
        try:
            prompt = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not prompt:
            break
        print("-" * 40)
        print(generate(prompt, max_new_tokens, ckpt_name))
    print("再见。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MiniLLM：数据/预训练/使用")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_train = sub.add_parser("train", help="预训练")
    p_train.add_argument("--data", required=True, help="utf-8 中文 txt 语料路径")
    p_train.add_argument("--steps", type=int, default=2000, help="训练步数")
    p_train.add_argument("--ckpt", default="minillm.pt", help="checkpoint 文件名")
    p_train.add_argument("--d-model", type=int, default=None, help="覆盖隐藏维度（默认 128）")
    p_train.add_argument("--n-layer", type=int, default=None, help="覆盖层数（默认 4）")
    p_train.add_argument("--n-head", type=int, default=None, help="覆盖注意力头数（默认 4）")

    p_gen = sub.add_parser("generate", help="生成")
    p_gen.add_argument("--prompt", default="", help="续写起始文本")
    p_gen.add_argument("--max-new-tokens", type=int, default=200, help="生成字符数")
    p_gen.add_argument("--ckpt", default="minillm.pt", help="checkpoint 文件名")
    p_gen.add_argument("--temperature", type=float, default=0.8, help="采样温度：越低越保守，越高越随机")
    p_gen.add_argument("--top-k", type=int, default=20, help="每步只在概率前 k 的字符里采样")

    p_chat = sub.add_parser("chat", help="交互测试模式")
    p_chat.add_argument("--ckpt", default="minillm.pt", help="checkpoint 文件名")
    p_chat.add_argument("--max-new-tokens", type=int, default=200, help="每次生成字符数")

    args = parser.parse_args()
    if args.cmd == "train":
        train(args.data, args.steps, args.ckpt, args.d_model, args.n_layer, args.n_head)
    elif args.cmd == "chat":
        chat(args.ckpt, args.max_new_tokens)
    else:
        print(generate(args.prompt, args.max_new_tokens, args.ckpt,
                       args.temperature, args.top_k))
