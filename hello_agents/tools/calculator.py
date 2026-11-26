# -*- coding: utf-8 -*-
"""自定义工具开发示例（教程 7.5.2）：基于 AST 的安全四则计算器。"""
import ast
import math
import operator

from hello_agents.tools.base import ToolRegistry

# 支持的运算符与函数白名单（AST 节点类型 -> 实现）
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}
_FUNCTIONS = {"sqrt": math.sqrt, "pi": math.pi}


def my_calculate(expression: str) -> str:
    """简单数学计算函数：解析表达式并安全求值。"""
    if not expression.strip():
        return "计算表达式不能为空"
    try:
        node = ast.parse(expression, mode="eval")
        result = _eval_node(node.body)
        return str(result)
    except Exception:
        return "计算失败，请检查表达式格式"


def _eval_node(node):
    """递归求值：只放行白名单内的运算，防代码注入。"""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) in _FUNCTIONS:
        return _FUNCTIONS[node.func.id](*[_eval_node(a) for a in node.args])
    if isinstance(node, ast.Name) and node.id in _FUNCTIONS:
        return _FUNCTIONS[node.id]
    raise ValueError(f"不支持的表达式元素: {ast.dump(node)}")


def create_calculator_registry() -> ToolRegistry:
    """创建包含计算器的工具注册表。"""
    registry = ToolRegistry()
    registry.register_function(
        name="my_calculator",
        description="简单的数学计算工具，支持基本运算(+,-,*,/,**)和sqrt函数、pi常数",
        func=my_calculate,
    )
    return registry
