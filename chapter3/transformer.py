# -*- coding: utf-8 -*-
"""第三章：补全版 Transformer（Encoder-Decoder）。

以 Hello-Agents 3.1.2 节的模块为基础，补齐教程缺失的部分：
  1. 词嵌入 + sqrt(d_model) 缩放
  2. Encoder / Decoder 多层堆叠与顶层 Transformer 装配类
  3. padding mask 与因果（look-ahead）mask 构造
  4. 输出头（Linear + Softmax）与贪心解码
运行: python transformer.py  # 内置序列反转小任务的自测
"""
import math

import torch
import torch.nn as nn


# ---------------- 教程已实现的模块（原样保留） ----------------

class MultiHeadAttention(nn.Module):
    """多头注意力机制模块。"""

    def __init__(self, d_model, num_heads):
        super(MultiHeadAttention, self).__init__()
        assert d_model % num_heads == 0, "d_model 必须能被 num_heads 整除"

        self.d_model = d_model
        self.num_heads = num_heads
        self.d_k = d_model // num_heads

        # Q, K, V 和输出的线性变换层
        self.W_q = nn.Linear(d_model, d_model)
        self.W_k = nn.Linear(d_model, d_model)
        self.W_v = nn.Linear(d_model, d_model)
        self.W_o = nn.Linear(d_model, d_model)

    def scaled_dot_product_attention(self, Q, K, V, mask=None):
        """缩放点积注意力。Q/K/V 形状 (batch, heads, seq, d_k)，mask 为 0 处不参与。"""
        attn_scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.d_k)
        if mask is not None:
            # 掩码为 0 的位置填充大负数，softmax 后权重趋近 0
            attn_scores = attn_scores.masked_fill(mask == 0, -1e9)
        attn_probs = torch.softmax(attn_scores, dim=-1)
        return torch.matmul(attn_probs, V)

    def split_heads(self, x):
        """(batch, seq, d_model) -> (batch, heads, seq, d_k)"""
        batch_size, seq_length, _ = x.size()
        return x.view(batch_size, seq_length, self.num_heads, self.d_k).transpose(1, 2)

    def combine_heads(self, x):
        """(batch, heads, seq, d_k) -> (batch, seq, d_model)"""
        batch_size, _, seq_length, _ = x.size()
        return x.transpose(1, 2).contiguous().view(batch_size, seq_length, self.d_model)

    def forward(self, Q, K, V, mask=None):
        Q = self.split_heads(self.W_q(Q))
        K = self.split_heads(self.W_k(K))
        V = self.split_heads(self.W_v(V))
        attn_output = self.scaled_dot_product_attention(Q, K, V, mask)
        return self.W_o(self.combine_heads(attn_output))


class PositionWiseFeedForward(nn.Module):
    """逐位置前馈网络：先扩大到 d_ff 再缩回 d_model。"""

    def __init__(self, d_model, d_ff, dropout=0.1):
        super(PositionWiseFeedForward, self).__init__()
        self.linear1 = nn.Linear(d_model, d_ff)
        self.dropout = nn.Dropout(dropout)
        self.linear2 = nn.Linear(d_ff, d_model)
        self.relu = nn.ReLU()

    def forward(self, x):
        x = self.linear1(x)
        x = self.relu(x)
        x = self.dropout(x)
        return self.linear2(x)


class PositionalEncoding(nn.Module):
    """正弦/余弦位置编码，偶数维 sin、奇数维 cos。"""

    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))

        pe = torch.zeros(max_len, d_model)
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        # buffer：不参与梯度更新，但随模型 to(device)
        self.register_buffer('pe', pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, :x.size(1)]
        return self.dropout(x)


# ---------------- 编码器 / 解码器核心层（教程骨架，参数已补齐） ----------------

class EncoderLayer(nn.Module):
    """编码器层：自注意力 + FFN，各带残差与 LayerNorm（Post-LN）。"""

    def __init__(self, d_model, num_heads, d_ff, dropout):
        super(EncoderLayer, self).__init__()
        self.self_attn = MultiHeadAttention(d_model, num_heads)
        self.feed_forward = PositionWiseFeedForward(d_model, d_ff, dropout)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, mask):
        attn_output = self.self_attn(x, x, x, mask)
        x = self.norm1(x + self.dropout(attn_output))
        ff_output = self.feed_forward(x)
        x = self.norm2(x + self.dropout(ff_output))
        return x


class DecoderLayer(nn.Module):
    """解码器层：掩码自注意力 -> 交叉注意力（看编码器输出）-> FFN。"""

    def __init__(self, d_model, num_heads, d_ff, dropout):
        super(DecoderLayer, self).__init__()
        self.self_attn = MultiHeadAttention(d_model, num_heads)
        self.cross_attn = MultiHeadAttention(d_model, num_heads)
        self.feed_forward = PositionWiseFeedForward(d_model, d_ff, dropout)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.norm3 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, encoder_output, src_mask, tgt_mask):
        attn_output = self.self_attn(x, x, x, tgt_mask)
        x = self.norm1(x + self.dropout(attn_output))

        cross_attn_output = self.cross_attn(x, encoder_output, encoder_output, src_mask)
        x = self.norm2(x + self.dropout(cross_attn_output))

        ff_output = self.feed_forward(x)
        x = self.norm3(x + self.dropout(ff_output))
        return x


# ---------------- 补全部分：mask、堆叠与顶层装配 ----------------

def create_pad_mask(seq, pad_idx):
    """padding 掩码：pad 位置为 0。形状 (batch, 1, 1, seq)，可广播到注意力得分。"""
    return (seq != pad_idx).unsqueeze(1).unsqueeze(2)


def create_causal_mask(size):
    """因果掩码：位置 i 只能看到 <= i 的词，防止偷看未来。形状 (1, size, size)。"""
    return torch.tril(torch.ones(size, size)).bool().unsqueeze(0)


class Encoder(nn.Module):
    """词嵌入 + 位置编码 + N 层编码器。"""

    def __init__(self, vocab_size, d_model, num_heads, d_ff, num_layers, dropout):
        super(Encoder, self).__init__()
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.pos_encoding = PositionalEncoding(d_model, dropout)
        self.layers = nn.ModuleList(
            [EncoderLayer(d_model, num_heads, d_ff, dropout) for _ in range(num_layers)])
        self.d_model = d_model

    def forward(self, x, mask):
        # 嵌入向量乘 sqrt(d_model)，与位置编码保持同一量级（原论文做法）
        x = self.embedding(x) * math.sqrt(self.d_model)
        x = self.pos_encoding(x)
        for layer in self.layers:
            x = layer(x, mask)
        return x


class Decoder(nn.Module):
    """词嵌入 + 位置编码 + N 层解码器。"""

    def __init__(self, vocab_size, d_model, num_heads, d_ff, num_layers, dropout):
        super(Decoder, self).__init__()
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.pos_encoding = PositionalEncoding(d_model, dropout)
        self.layers = nn.ModuleList(
            [DecoderLayer(d_model, num_heads, d_ff, dropout) for _ in range(num_layers)])
        self.d_model = d_model

    def forward(self, x, encoder_output, src_mask, tgt_mask):
        x = self.embedding(x) * math.sqrt(self.d_model)
        x = self.pos_encoding(x)
        for layer in self.layers:
            x = layer(x, encoder_output, src_mask, tgt_mask)
        return x


class Transformer(nn.Module):
    """完整 Encoder-Decoder Transformer。

    src/tgt 均为词元 id 序列 (batch, seq)；pad_idx 用于构造 padding 掩码，
    目标端额外叠加因果掩码。
    """

    def __init__(self, src_vocab_size, tgt_vocab_size, d_model=512, num_heads=8,
                 d_ff=2048, num_layers=6, dropout=0.1, pad_idx=0):
        super(Transformer, self).__init__()
        self.pad_idx = pad_idx
        self.encoder = Encoder(src_vocab_size, d_model, num_heads, d_ff, num_layers, dropout)
        self.decoder = Decoder(tgt_vocab_size, d_model, num_heads, d_ff, num_layers, dropout)
        # 输出头：映射到目标词表，softmax 在损失函数内部做
        self.output_projection = nn.Linear(d_model, tgt_vocab_size)

    def forward(self, src, tgt):
        src_mask = create_pad_mask(src, self.pad_idx)
        # 目标掩码 = padding 掩码 与 因果掩码 的交集
        tgt_pad = create_pad_mask(tgt, self.pad_idx)
        tgt_causal = create_causal_mask(tgt.size(1)).to(tgt.device)
        tgt_mask = tgt_pad & tgt_causal

        encoder_output = self.encoder(src, src_mask)
        decoder_output = self.decoder(tgt, encoder_output, src_mask, tgt_mask)
        return self.output_projection(decoder_output)

    @torch.no_grad()
    def greedy_decode(self, src, max_len, bos_idx, eos_idx):
        """贪心解码：从 BOS 开始，每步取概率最大的词元，直到 EOS 或达到 max_len。"""
        self.eval()
        src = src.to(next(self.parameters()).device)
        memory = self.encoder(src, create_pad_mask(src, self.pad_idx))

        ys = torch.full((src.size(0), 1), bos_idx, dtype=torch.long, device=src.device)
        finished = torch.zeros(src.size(0), dtype=torch.bool, device=src.device)
        for _ in range(max_len - 1):
            # 解码端因果掩码在 forward 内构造；这里直接调 decoder 拼装好的 forward
            logits = self.forward(src, ys)
            next_token = logits[:, -1].argmax(dim=-1, keepdim=True)
            # 已结束的序列冻结为 pad，不再增长
            next_token[finished] = self.pad_idx
            ys = torch.cat([ys, next_token], dim=1)
            finished |= next_token.squeeze(1).eq(eos_idx)
            if finished.all():
                break
        return ys


# ---------------- 自测：序列反转任务 ----------------

def demo():
    """训练一个迷你 Transformer 学会反转数字序列，验证前向/掩码/解码全链路。"""
    torch.manual_seed(0)
    PAD, BOS, EOS = 0, 1, 2
    VOCAB = 10  # 词表: 0=pad 1=bos 2=eos 3..9=数据词元
    model = Transformer(src_vocab_size=VOCAB, tgt_vocab_size=VOCAB,
                        d_model=64, num_heads=4, d_ff=128, num_layers=2,
                        dropout=0.0, pad_idx=PAD)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss(ignore_index=PAD)

    def make_batch(batch_size=32, seq_len=6):
        # 数据词元范围 [3, VOCAB)，源与目标为同一序列的反转
        data = torch.randint(3, VOCAB, (batch_size, seq_len))
        src = data
        # 教师强制目标：BOS + 反转序列（输入），反转序列 + EOS（标签）
        tgt_in = torch.cat([torch.full((batch_size, 1), BOS), data.flip(1)], dim=1)
        tgt_out = torch.cat([data.flip(1), torch.full((batch_size, 1), EOS)], dim=1)
        return src, tgt_in, tgt_out

    # 训练并断言损失下降
    first_loss = None
    for step in range(1, 5001):
        src, tgt_in, tgt_out = make_batch()
        logits = model(src, tgt_in)
        loss = criterion(logits.reshape(-1, VOCAB), tgt_out.reshape(-1))
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        if step == 1:
            first_loss = loss.item()
    assert loss.item() < first_loss * 0.5, f"损失未下降: {first_loss:.3f} -> {loss.item():.3f}"
    print(f"训练完成: loss {first_loss:.3f} -> {loss.item():.3f}")

    # 贪心解码验证反转效果
    src, _, _ = make_batch(batch_size=3)
    output = model.greedy_decode(src, max_len=10, bos_idx=BOS, eos_idx=EOS)
    for i in range(3):
        expected = src[i].flip(0).tolist()
        decoded = [t for t in output[i].tolist() if t not in (PAD, BOS, EOS)]
        print(f"源序列: {src[i].tolist()} -> 期望反转: {expected} -> 模型输出: {decoded}")
        assert decoded == expected, f"反转结果不符: {decoded} != {expected}"
    print("自测通过 ✅")


if __name__ == "__main__":
    demo()
