from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from app.schemas.transaction import TransactionAction


class TokenType(Enum):
    EOF = "EOF"
    IDENTIFIER = "IDENTIFIER"
    NUMBER = "NUMBER"
    STRING = "STRING"
    EQUAL = "=="
    NOT_EQUAL = "!="
    GREATER = ">"
    GREATER_EQUAL = ">="
    LESS = "<"
    LESS_EQUAL = "<="
    AND = "and"
    OR = "or"
    NOT = "not"
    IS = "is"
    NONE = "None"
    LPAREN = "("
    RPAREN = ")"


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: Any
    position: int


class Lexer:
    KEYWORDS = {
        "and": TokenType.AND,
        "or": TokenType.OR,
        "not": TokenType.NOT,
        "is": TokenType.IS,
        "None": TokenType.NONE,
    }

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.current_char = self.text[0] if text else None

    def advance(self):
        self.pos += 1
        self.current_char = self.text[self.pos] if self.pos < len(self.text) else None

    def skip_whitespace(self):
        while self.current_char is not None and self.current_char.isspace():
            self.advance()

    def peek(self, n: int = 1) -> Optional[str]:
        peek_pos = self.pos + n
        return self.text[peek_pos] if peek_pos < len(self.text) else None

    def read_string(self) -> str:
        quote = self.current_char
        self.advance()
        result = []
        while self.current_char is not None and self.current_char != quote:
            if self.current_char == "\\":
                self.advance()
                if self.current_char in ('"', "'", "\\", "n", "t", "r"):
                    result.append({"n": "\n", "t": "\t", "r": "\r"}.get(self.current_char, self.current_char))
                else:
                    result.append(self.current_char)
            else:
                result.append(self.current_char)
            self.advance()
        if self.current_char == quote:
            self.advance()
        return "".join(result)

    def read_number(self) -> float:
        result = []
        while self.current_char is not None and (self.current_char.isdigit() or self.current_char == "."):
            result.append(self.current_char)
            self.advance()
        return float("".join(result))

    def read_identifier(self) -> str:
        result = []
        while self.current_char is not None and (self.current_char.isalnum() or self.current_char == "_"):
            result.append(self.current_char)
            self.advance()
        return "".join(result)

    def next_token(self) -> Token:
        while self.current_char is not None:
            if self.current_char.isspace():
                self.skip_whitespace()
                continue

            if self.current_char in ('"', "'"):
                start = self.pos
                str_value = self.read_string()
                return Token(TokenType.STRING, str_value, start)

            if self.current_char.isdigit():
                start = self.pos
                num_value = self.read_number()
                return Token(TokenType.NUMBER, num_value, start)

            if self.current_char.isalpha() or self.current_char == "_":
                start = self.pos
                ident_value = self.read_identifier()
                token_type = self.KEYWORDS.get(ident_value, TokenType.IDENTIFIER)
                return Token(token_type, ident_value, start)

            if self.current_char == "=" and self.peek() == "=":
                self.advance()
                self.advance()
                return Token(TokenType.EQUAL, "==", self.pos - 1)

            if self.current_char == "!" and self.peek() == "=":
                self.advance()
                self.advance()
                return Token(TokenType.NOT_EQUAL, "!=", self.pos - 1)

            if self.current_char == ">" and self.peek() == "=":
                self.advance()
                self.advance()
                return Token(TokenType.GREATER_EQUAL, ">=", self.pos - 1)

            if self.current_char == "<" and self.peek() == "=":
                self.advance()
                self.advance()
                return Token(TokenType.LESS_EQUAL, "<=", self.pos - 1)

            if self.current_char == ">":
                self.advance()
                return Token(TokenType.GREATER, ">", self.pos - 1)

            if self.current_char == "<":
                self.advance()
                return Token(TokenType.LESS, "<", self.pos - 1)

            if self.current_char == "(":
                self.advance()
                return Token(TokenType.LPAREN, "(", self.pos - 1)

            if self.current_char == ")":
                self.advance()
                return Token(TokenType.RPAREN, ")", self.pos - 1)

            raise ValueError(f"Unexpected character: {self.current_char} at position {self.pos}")

        return Token(TokenType.EOF, None, self.pos)


class ASTNode:
    pass


@dataclass
class BinaryOp(ASTNode):
    left: ASTNode
    operator: TokenType
    right: ASTNode


@dataclass
class UnaryOp(ASTNode):
    operator: TokenType
    operand: ASTNode


@dataclass
class Variable(ASTNode):
    name: str


@dataclass
class Literal(ASTNode):
    value: Any


@dataclass
class IsNone(ASTNode):
    expr: ASTNode


class Parser:
    def __init__(self, lexer: Lexer):
        self.lexer = lexer
        self.current_token = self.lexer.next_token()

    def eat(self, token_type: TokenType):
        if self.current_token.type == token_type:
            self.current_token = self.lexer.next_token()
        else:
            raise ValueError(f"Expected {token_type}, got {self.current_token.type}")

    def parse(self) -> ASTNode:
        node = self.parse_or()
        if self.current_token.type != TokenType.EOF:
            raise ValueError(f"Unexpected token at end: {self.current_token}")
        return node

    def parse_or(self) -> ASTNode:
        node = self.parse_and()
        while self.current_token.type == TokenType.OR:
            token = self.current_token
            self.eat(TokenType.OR)
            node = BinaryOp(node, token.type, self.parse_and())
        return node

    def parse_and(self) -> ASTNode:
        node = self.parse_not()
        while self.current_token.type == TokenType.AND:
            token = self.current_token
            self.eat(TokenType.AND)
            node = BinaryOp(node, token.type, self.parse_not())
        return node

    def parse_not(self) -> ASTNode:
        if self.current_token.type == TokenType.NOT:
            token = self.current_token
            self.eat(TokenType.NOT)
            return UnaryOp(token.type, self.parse_not())
        return self.parse_comparison()

    def parse_comparison(self) -> ASTNode:
        node = self.parse_primary()

        while self.current_token.type in (
            TokenType.EQUAL,
            TokenType.NOT_EQUAL,
            TokenType.GREATER,
            TokenType.GREATER_EQUAL,
            TokenType.LESS,
            TokenType.LESS_EQUAL,
        ):
            token = self.current_token
            self.eat(token.type)
            right = self.parse_primary()
            node = BinaryOp(node, token.type, right)

        if self.current_token.type == TokenType.IS:
            self.eat(TokenType.IS)
            if self.current_token.type == TokenType.NOT:
                self.eat(TokenType.NOT)
                self.eat(TokenType.NONE)
                # "is not None" -> not (is None)
                return UnaryOp(TokenType.NOT, IsNone(node))
            if self.current_token.type == TokenType.NONE:
                self.eat(TokenType.NONE)
                # "is None" -> is None check
                return IsNone(node)

        return node

    def parse_primary(self) -> ASTNode:
        token = self.current_token

        if token.type == TokenType.NUMBER:
            self.eat(TokenType.NUMBER)
            return Literal(token.value)

        if token.type == TokenType.STRING:
            self.eat(TokenType.STRING)
            return Literal(token.value)

        if token.type == TokenType.NONE:
            self.eat(TokenType.NONE)
            return Literal(None)

        if token.type == TokenType.IDENTIFIER:
            self.eat(TokenType.IDENTIFIER)
            return Variable(token.value)

        if token.type == TokenType.LPAREN:
            self.eat(TokenType.LPAREN)
            node = self.parse_or()
            self.eat(TokenType.RPAREN)
            return node

        if token.type == TokenType.NOT:
            self.eat(TokenType.NOT)
            return UnaryOp(TokenType.NOT, self.parse_primary())

        raise ValueError(f"Unexpected token: {token}")


class Evaluator:
    def __init__(self, context: dict):
        self.context = context

    def evaluate(self, node: ASTNode) -> Any:
        if isinstance(node, Literal):
            return node.value

        if isinstance(node, Variable):
            if node.name not in self.context:
                raise ValueError(f"Unknown variable: {node.name}")
            return self.context[node.name]

        if isinstance(node, UnaryOp):
            operand = self.evaluate(node.operand)
            if node.operator == TokenType.NOT:
                return not operand
            if node.operator == TokenType.IS:
                return operand is None
            raise ValueError(f"Unknown unary operator: {node.operator}")

        if isinstance(node, IsNone):
            return self.evaluate(node.expr) is None

        if isinstance(node, BinaryOp):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)

            if node.operator == TokenType.AND:
                return left and right
            if node.operator == TokenType.OR:
                return left or right
            if node.operator == TokenType.EQUAL:
                return left == right
            if node.operator == TokenType.NOT_EQUAL:
                return left != right
            if node.operator == TokenType.GREATER:
                return left > right
            if node.operator == TokenType.GREATER_EQUAL:
                return left >= right
            if node.operator == TokenType.LESS:
                return left < right
            if node.operator == TokenType.LESS_EQUAL:
                return left <= right
            raise ValueError(f"Unknown binary operator: {node.operator}")

        raise ValueError(f"Unknown AST node: {type(node)}")


def parse_expression(expression: str) -> ASTNode:
    lexer = Lexer(expression)
    parser = Parser(lexer)
    return parser.parse()


def evaluate_expression(expression: str, context: dict) -> bool:
    try:
        ast = parse_expression(expression)
        evaluator = Evaluator(context)
        result = evaluator.evaluate(ast)
        return bool(result)
    except Exception:
        return False


@dataclass(frozen=True)
class Rule:
    id: UUID
    name: str
    dsl_expression: str
    action: TransactionAction
    priority: int
    enabled: bool
    version: int


@dataclass(frozen=True)
class TriggeredRule:
    rule_id: UUID
    rule_name: str
    action: TransactionAction
    priority: int
    dsl_expression: str


@dataclass(frozen=True)
class RuleEngineResult:
    final_action: TransactionAction
    triggered_rules: list[TriggeredRule]
    risk_score: Optional[float]


class RuleEngine:
    ACTION_PRECEDENCE = {
        TransactionAction.BLOCK: 3,
        TransactionAction.REVIEW: 2,
        TransactionAction.ALLOW: 1,
    }

    def __init__(self, rules: list[Rule]):
        self.rules = sorted(
            [r for r in rules if r.enabled],
            key=lambda r: r.priority,
        )

    def evaluate(self, transaction_data: dict) -> RuleEngineResult:
        triggered = []
        for rule in self.rules:
            if self._evaluate_rule(rule, transaction_data):
                triggered.append(
                    TriggeredRule(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        action=rule.action,
                        priority=rule.priority,
                        dsl_expression=rule.dsl_expression,
                    )
                )

        final_action = self._resolve_action(triggered)
        risk_score = self._calculate_risk_score(triggered, transaction_data, final_action)

        return RuleEngineResult(
            final_action=final_action,
            triggered_rules=triggered,
            risk_score=risk_score,
        )

    def _evaluate_rule(self, rule: Rule, transaction_data: dict) -> bool:
        try:
            return self._evaluate_dsl(rule.dsl_expression, transaction_data)
        except Exception:
            return False

    def _evaluate_dsl(self, expression: str, data: dict) -> bool:
        safe_dict = {
            "amount": data.get("amount"),
            "currency": data.get("currency"),
            "customer_risk_tier": data.get("customer_risk_tier"),
            "customer_kyc_status": data.get("customer_kyc_status"),
            "device_risk_score": data.get("device_risk_score"),
            "merchant_category_code": data.get("merchant_category_code"),
            "merchant_risk_level": data.get("merchant_risk_level"),
        }

        return evaluate_expression(expression, safe_dict)

    def _resolve_action(self, triggered_rules: list[TriggeredRule]) -> TransactionAction:
        if not triggered_rules:
            return TransactionAction.ALLOW

        max_precedence = max(
            self.ACTION_PRECEDENCE.get(r.action, 0) for r in triggered_rules
        )

        for action, precedence in self.ACTION_PRECEDENCE.items():
            if precedence == max_precedence:
                return action

        return TransactionAction.ALLOW

    def _calculate_risk_score(
        self, triggered_rules: list[TriggeredRule], transaction_data: dict, final_action: TransactionAction
    ) -> float:
        if not triggered_rules:
            return 0.0

        max_precedence = max(
            self.ACTION_PRECEDENCE.get(r.action, 0) for r in triggered_rules
        )
        base_score = (max_precedence / 3.0) * 40.0

        amount = transaction_data.get("amount", 0)
        if isinstance(amount, Decimal):
            amount = float(amount)

        amount_factor = min(amount / 50000.0, 0.3)

        customer_risk = transaction_data.get("customer_risk_tier", "standard")
        customer_factor = {"low": -0.1, "standard": 0.0, "high": 0.15, "critical": 0.25}.get(
            customer_risk, 0.0
        )

        device_risk = transaction_data.get("device_risk_score")
        device_factor = float(device_risk) * 0.2 if device_risk is not None else 0.0

        merchant_risk = transaction_data.get("merchant_risk_level", "standard")
        merchant_factor = {"low": -0.05, "standard": 0.0, "high": 0.1, "critical": 0.2}.get(
            merchant_risk, 0.0
        )

        score = base_score + (amount_factor * 100) + (customer_factor * 100) + (device_factor * 100) + (merchant_factor * 100)
        return max(0.0, min(100.0, score))