# -*- coding: utf-8 -*-
"""第六章：基于 AgentScope 2.x 的三国狼人杀多智能体游戏。

参考教程：https://hello-agents.datawhale.cc/#/./chapter6/第六章%20框架开发实践（6.3.2 节）
教程基于 AgentScope 1.x 的 MsgHub/fanout_pipeline；当前安装的 2.x 移除了这些组件，
本地适配方案：
  - MsgHub 私密频道  -> 狼人阶段用「仅狼人互相 observe」模拟广播
  - fanout_pipeline  -> asyncio.gather 并行收集投票（结构化输出）
  - 主持人 announce  -> 纯消息工厂函数（不消耗 LLM）
运行:
  ANTHROPIC_MODEL='gpt-6.1-terra[1m]' .venv/bin/python chapter6/werewolf.py
"""
import asyncio
import os
import sys

from pydantic import BaseModel, Field

from agentscope.agent import Agent
from agentscope.credential import AnthropicCredential
from agentscope.message import Msg, UserMsg
from agentscope.model import AnthropicChatModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.llm_client import load_env

load_env()

MAX_ROUNDS = 5        # 最大游戏轮数，防止无限循环
MAX_DISCUSSION = 1    # 每个阶段每名玩家的发言次数


# ---------------- 结构化输出模型：用数据模型约束游戏规则 ----------------

class StatementModel(BaseModel):
    """自由发言的输出格式。"""
    statement: str = Field(description="以三国人物口吻发表的发言")


class WolfKillModel(BaseModel):
    """狼人击杀决策的输出格式。"""
    target: str = Field(description="要击杀的玩家名，必须是存活玩家")


class SeerCheckModel(BaseModel):
    """预言家查验决策的输出格式。"""
    target: str = Field(description="要查验的玩家名，必须是存活且非自己的玩家")


class WitchActionModel(BaseModel):
    """女巫行动的输出格式。"""
    use_antidote: bool = Field(description="是否使用解药救今晚的受害者")
    use_poison: bool = Field(description="是否使用毒药")
    poison_target: str | None = Field(description="毒药目标玩家名，不使用则为 null", default=None)


class VoteModel(BaseModel):
    """白天放逐投票的输出格式。"""
    target: str = Field(description="投票放逐的玩家名，必须是存活玩家")
    reason: str = Field(description="投票理由")


# ---------------- 角色提示词：游戏角色 + 三国人格双重建模 ----------------

PERSONALITY = {
    "孙权": "你善于权衡制衡，讲话谨慎稳重，善于联合他人。",
    "周瑜": "你才华横溢但心胸不算宽广，说话文雅带机锋，善用谋略。",
    "曹操": "你雄猜多疑、枭雄气概，说话霸气直接，宁负天下人。",
    "张飞": "你勇猛鲁莽、嫉恶如仇，说话大声粗犷，直来直去。",
    "司马懿": "你深藏不露、隐忍老练，说话滴水不漏，善于后发制人。",
    "赵云": "你忠勇正直、行事磊落，说话诚恳条理清晰。",
}

ROLE_RULES = {
    "狼人": "你是狼人阵营。夜晚与同伴协商击杀一名好人；白天必须隐藏身份，误导好人投票。",
    "预言家": "你是预言家。每晚查验一名玩家的阵营；白天可适当公开信息带领好人，但也要小心被狼人针对。",
    "女巫": "你是女巫。有一瓶解药（救今晚被杀者）和一瓶毒药（毒死一人），各只能用一次；白天隐藏身份。",
    "村民": "你是好人村民，没有特殊技能。靠倾听和推理找出狼人。",
}


def build_player(name: str, role: str, model, all_players: list[str]) -> Agent:
    """创建一名玩家智能体：系统提示词 = 三国人格 + 游戏角色规则。"""
    system_prompt = f"""你是{name}，在这场三国狼人杀游戏中扮演{role}。
共 {len(all_players)} 名玩家：{('、'.join(all_players))}。

人物性格：{PERSONALITY[name]}

游戏规则：{ROLE_RULES[role]}

要求：
1. 只通过对话和推理参与游戏，不要尝试调用任何外部工具
2. 发言保持{name}的三国口吻，简洁有力（两三句话）"""
    return Agent(name=name, system_prompt=system_prompt, model=model)


# ---------------- 游戏控制器 ----------------

class ThreeKingdomsWerewolf:
    """游戏主控制器：维护全局状态，推进夜晚/白天阶段，裁定胜负。

    分层：本类是游戏控制层；玩家间通信走消息广播（交互层）；
    每个玩家的双重身份建模在其系统提示词中（角色层）。
    """

    def __init__(self, model):
        self.roles = {
            "孙权": "狼人", "周瑜": "狼人",
            "曹操": "预言家", "张飞": "女巫",
            "司马懿": "村民", "赵云": "村民",
        }
        self.players = {name: build_player(name, role, model, list(self.roles))
                        for name, role in self.roles.items()}
        self.alive = list(self.roles)
        self.seer_knowledge: dict[str, str] = {}   # key 为被查验玩家名
        self.witch_used = {"antidote": False, "poison": False}
        print(f"🎮 三国狼人杀开始！玩家：{'、'.join(self.alive)}")
        for name, role in self.roles.items():
            print(f"   （{name} = {role}）")

    # --- 基础工具 ---

    def announce(self, text: str) -> UserMsg:
        """主持人生成一条公告消息（不消耗 LLM）。"""
        print(f"\n📢 {text}")
        return UserMsg(name="主持人", content=text)

    @staticmethod
    async def broadcast(speaker_msg: Msg, listeners: list[Agent]):
        """广播：让除发言者外的所有听众 observe 这条消息（2.x 的 MsgHub 替代）。"""
        for listener in listeners:
            await listener.observe(speaker_msg)

    def wolves(self) -> list[Agent]:
        """返回存活的狼人玩家列表。"""
        return [self.players[n] for n in self.alive if self.roles[n] == "狼人"]

    def alive_others(self, name: str) -> list[str]:
        """返回除 name 外的存活玩家名列表。"""
        return [n for n in self.alive if n != name]

    async def ask(self, player: Agent, msg: UserMsg, schema=None):
        """带容错的单次询问：LLM/解析失败时返回默认值，保证游戏继续。"""
        try:
            reply = await player.reply(msg, structured_schema=schema)
            await self.broadcast(reply, [p for p in self.players.values() if p is not player])
            return reply.structured_output if schema else reply.get_text_content()
        except Exception as e:
            print(f"⚠️ {player.name} 出错: {e}")
            if schema is StatementModel:
                return StatementModel(statement="（一时语塞，未能发言）").model_dump()
            if schema is VoteModel:
                return VoteModel(target=self.alive_others(player.name)[0], reason="随机投出").model_dump()
            return None

    # --- 夜晚阶段 ---

    async def night_phase(self, round_num: int):
        """夜晚：狼人击杀 -> 预言家查验 -> 女巫用药。返回今晚死亡名单。"""
        print(f"\n🌙 第{round_num}夜降临，天黑请闭眼...")

        # 1. 狼人私密频道：只有狼人互相 observe 对方的讨论
        wolves = self.wolves()
        kill_target = None
        if wolves:
            msg = self.announce(f"🐺 狼人请睁眼！存活玩家：{'、'.join(self.alive)}。请协商击杀目标。")
            for _ in range(MAX_DISCUSSION):
                for wolf in wolves:
                    reply = await wolf.reply(msg, structured_schema=StatementModel)
                    print(f"   {wolf.name}: {reply.structured_output['statement']}")
                    # 私密广播：仅狼人可见
                    for other in wolves:
                        if other is not wolf:
                            await other.observe(reply)
            votes = await asyncio.gather(*[
                self._ask_quiet(wolf, f"请确定今晚的击杀目标（从存活玩家中选）。", WolfKillModel)
                for wolf in wolves])
            valid = [v["target"] for v in votes if v and v.get("target") in self.alive]
            if valid:
                kill_target = max(set(valid), key=valid.count)
        print(f"   （狼人最终决定击杀：{kill_target}）")

        # 2. 预言家查验
        seer = self.players.get("曹操") if "曹操" in self.alive else None
        if seer:
            check = await self._ask_quiet(
                seer, f"预言家请睁眼。你要查验谁？存活玩家：{'、'.join(self.alive_others('曹操'))}",
                SeerCheckModel)
            if check and check["target"] in self.alive:
                result = "狼人" if self.roles[check["target"]] == "狼人" else "好人"
                self.seer_knowledge[check["target"]] = result
                # 查验结果私密告知预言家
                await seer.observe(self.announce(f"🔮 查验结果：{check['target']} 是{result}"))

        # 3. 女巫用药
        deaths = []
        witch = self.players.get("张飞") if "张飞" in self.alive else None
        if witch and kill_target:
            info = f"女巫请睁眼。今晚 {kill_target} 被袭击。"
            if not self.witch_used["antidote"]:
                info += "你还有解药。"
            if not self.witch_used["poison"]:
                info += f"你还有毒药，可毒杀一名玩家：{'、'.join(self.alive_others('张飞'))}。"
            info += "如何行动？（解药/毒药各仅一次）"
            action = await self._ask_quiet(witch, info, WitchActionModel)
            if action:
                if action.get("use_antidote") and not self.witch_used["antidote"]:
                    self.witch_used["antidote"] = True
                    kill_target = None
                    print("   （女巫使用了解药，受害者获救）")
                if action.get("use_poison") and not self.witch_used["poison"] \
                        and action.get("poison_target") in self.alive:
                    self.witch_used["poison"] = True
                    deaths.append(action["poison_target"])
                    print(f"   （女巫毒杀了 {action['poison_target']}）")
        if kill_target:
            deaths.append(kill_target)
        return deaths

    async def _ask_quiet(self, player: Agent, content: str, schema):
        """私密询问：回复不广播，只返回结构化结果（用于夜晚行动）。"""
        try:
            reply = await player.reply(UserMsg(name="主持人", content=content),
                                       structured_schema=schema)
            return reply.structured_output
        except Exception as e:
            print(f"⚠️ {player.name} 夜间行动出错: {e}")
            return None

    # --- 白天阶段 ---

    async def day_phase(self, round_num: int, deaths: list[str]):
        """白天：公布死讯 -> 自由讨论 -> 投票放逐。返回被放逐者。"""
        print(f"\n☀️ 第{round_num}天天亮了。昨夜死亡：{'、'.join(deaths) if deaths else '无人（平安夜）'}")
        for name in deaths:
            self.alive.remove(name)

        # 1. 全员自由讨论（公开广播）
        msg = self.announce(
            f"自由讨论阶段。存活玩家：{'、'.join(self.alive)}。请分析局势，找出狼人。")
        for _ in range(MAX_DISCUSSION):
            for name in list(self.alive):
                statement = await self.ask(self.players[name], msg, StatementModel)
                if statement:
                    print(f"   {name}: {statement['statement']}")

        # 2. 并行投票（fanout_pipeline 的 2.x 等价：asyncio.gather）
        msg = self.announce(f"请投票放逐一名玩家。候选人：{'、'.join(self.alive)}")
        votes = await asyncio.gather(*[
            self.players[name].reply(UserMsg(name="主持人", content=msg.content),
                                     structured_schema=VoteModel)
            for name in self.alive])
        tally: dict[str, int] = {}
        for voter, reply in zip(self.alive, votes):
            try:
                target = reply.structured_output["target"]
            except Exception:
                continue
            if target in self.alive:
                tally[target] = tally.get(target, 0) + 1
                print(f"   🗳️ {voter} -> {target}（{reply.structured_output.get('reason', '')}）")
        if not tally:
            return None
        ejected = max(tally, key=tally.get)
        print(f"   ⚖️ 放逐结果：{ejected}（{tally[ejected]} 票）—— 真实身份：{self.roles[ejected]}")
        self.alive.remove(ejected)
        return ejected

    # --- 胜负判定 ---

    def check_winner(self) -> str | None:
        """判定胜负：狼人全灭则好人胜；狼人数 >= 好人数则狼人胜。"""
        wolves = sum(1 for n in self.alive if self.roles[n] == "狼人")
        good = len(self.alive) - wolves
        if wolves == 0:
            return "好人阵营获胜！🎉"
        if wolves >= good:
            return "狼人阵营获胜！🐺"
        return None

    async def run(self):
        """主循环：夜昼交替，直到分出胜负或达到最大轮数。"""
        for round_num in range(1, MAX_ROUNDS + 1):
            deaths = await self.night_phase(round_num)
            winner = self.check_winner()
            if winner:
                print(f"\n🏆 {winner}")
                return
            ejected = await self.day_phase(round_num, deaths)
            winner = self.check_winner()
            if winner:
                print(f"\n🏆 {winner}")
                return
        print("\n⏰ 达到最大轮数，游戏结束。")


def main():
    """构建模型与游戏并运行。"""
    model = AnthropicChatModel(
        credential=AnthropicCredential(
            api_key=os.environ["ANTHROPIC_AUTH_TOKEN"],
            base_url=os.environ["ANTHROPIC_BASE_URL"],
        ),
        model=os.environ["ANTHROPIC_MODEL"],
        stream=False,
    )
    asyncio.run(ThreeKingdomsWerewolf(model).run())


if __name__ == "__main__":
    main()
