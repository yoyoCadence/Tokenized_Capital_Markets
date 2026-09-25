"""Safe arithmetic and predicate expressions; no Python eval or function calls."""
import ast
import math
import operator


class ExpressionError(ValueError):
    pass


OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow}
CMPS = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
        ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}


def names(expression):
    tree = ast.parse(expression, mode="eval")
    # This also rejects unsafe nodes when checking the expression.
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name):
            return {node.id}
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return set()
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return visit(node.left) | visit(node.right)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return visit(node.operand)
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            return set().union(*(visit(x) for x in node.values))
        if isinstance(node, ast.Compare) and all(type(x) in CMPS for x in node.ops):
            return visit(node.left) | set().union(*(visit(x) for x in node.comparators))
        raise ExpressionError(f"Disallowed expression node: {type(node).__name__}")
    return visit(tree)


def evaluate(expression, variables):
    required = names(expression)
    if missing := required - variables.keys():
        raise ExpressionError(f"Missing expression inputs: {sorted(missing)}")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name):
            return variables[node.id]
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e100):
                raise ExpressionError("Exponent exceeds safe bounds")
            return OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for op, next_node in zip(node.ops, node.comparators):
                right = visit(next_node)
                if not CMPS[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(visit(x) for x in node.values)
            return any(visit(x) for x in node.values)
        raise ExpressionError("Unsafe expression")

    result = visit(ast.parse(expression, mode="eval"))
    if type(result) in (float, int) and not math.isfinite(result):
        raise ExpressionError("Non-finite result")
    return result
