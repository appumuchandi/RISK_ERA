from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.rule_engine import (
    RuleEngine,
    Rule,
    TransactionAction,
    parse_expression,
    evaluate_expression,
    Lexer,
    Evaluator,
    TokenType,
    BinaryOp,
    Variable,
    Literal,
    UnaryOp,
    IsNone,
)


class TestLexer:
    def test_tokenize_identifiers(self):
        lexer = Lexer("amount")
        token = lexer.next_token()
        assert token.type == TokenType.IDENTIFIER
        assert token.value == "amount"

    def test_tokenize_numbers(self):
        lexer = Lexer("100")
        token = lexer.next_token()
        assert token.type == TokenType.NUMBER
        assert token.value == 100.0

        lexer = Lexer("100.50")
        token = lexer.next_token()
        assert token.value == 100.50

    def test_tokenize_strings(self):
        lexer = Lexer('"USD"')
        token = lexer.next_token()
        assert token.type == TokenType.STRING
        assert token.value == "USD"

        lexer = Lexer("'EUR'")
        token = lexer.next_token()
        assert token.value == "EUR"

    def test_tokenize_operators(self):
        test_cases = [
            ("==", TokenType.EQUAL),
            ("!=", TokenType.NOT_EQUAL),
            (">", TokenType.GREATER),
            (">=", TokenType.GREATER_EQUAL),
            ("<", TokenType.LESS),
            ("<=", TokenType.LESS_EQUAL),
            ("and", TokenType.AND),
            ("or", TokenType.OR),
            ("not", TokenType.NOT),
            ("is", TokenType.IS),
            ("None", TokenType.NONE),
        ]
        for text, expected in test_cases:
            lexer = Lexer(text)
            token = lexer.next_token()
            assert token.type == expected, f"Failed for {text}"

    def test_tokenize_parentheses(self):
        lexer = Lexer("()")
        assert lexer.next_token().type == TokenType.LPAREN
        assert lexer.next_token().type == TokenType.RPAREN


class TestParser:
    def test_parse_literal(self):
        ast = parse_expression("100")
        assert isinstance(ast, Literal)
        assert ast.value == 100.0

        ast = parse_expression('"USD"')
        assert isinstance(ast, Literal)
        assert ast.value == "USD"

    def test_parse_variable(self):
        ast = parse_expression("amount")
        assert isinstance(ast, Variable)
        assert ast.name == "amount"

    def test_parse_comparison(self):
        ast = parse_expression("amount > 100")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == TokenType.GREATER
        assert isinstance(ast.left, Variable)
        assert isinstance(ast.right, Literal)

    def test_parse_logical_and(self):
        ast = parse_expression("amount > 100 and currency == 'USD'")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == TokenType.AND

    def test_parse_logical_or(self):
        ast = parse_expression("amount > 100 or amount < 10")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == TokenType.OR

    def test_parse_not(self):
        ast = parse_expression("not amount > 100")
        assert isinstance(ast, UnaryOp)
        assert ast.operator == TokenType.NOT

    def test_parse_parentheses(self):
        ast = parse_expression("(amount > 100) and (currency == 'USD')")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == TokenType.AND

    def test_parse_precedence(self):
        ast = parse_expression("amount > 100 or amount < 10 and currency == 'USD'")
        assert isinstance(ast, BinaryOp)
        assert ast.operator == TokenType.OR

    def test_parse_is_none(self):
        ast = parse_expression("device_risk_score is None")
        assert isinstance(ast, IsNone)

    def test_parse_is_not_none(self):
        ast = parse_expression("device_risk_score is not None")
        assert isinstance(ast, UnaryOp)
        assert ast.operator == TokenType.NOT
        assert isinstance(ast.operand, IsNone)


class TestEvaluator:
    def test_evaluate_literal(self):
        ast = Literal(100)
        evaluator = Evaluator({})
        assert evaluator.evaluate(ast) == 100

        ast = Literal("USD")
        assert evaluator.evaluate(ast) == "USD"

    def test_evaluate_variable(self):
        ast = Variable("amount")
        evaluator = Evaluator({"amount": Decimal("100.00")})
        assert evaluator.evaluate(ast) == Decimal("100.00")

    def test_evaluate_comparison(self):
        ast = parse_expression("amount > 100")
        evaluator = Evaluator({"amount": Decimal("150.00")})
        assert evaluator.evaluate(ast) is True

        evaluator = Evaluator({"amount": Decimal("50.00")})
        assert evaluator.evaluate(ast) is False

    def test_evaluate_logical_and(self):
        ast = parse_expression("amount > 100 and currency == 'USD'")
        evaluator = Evaluator({"amount": Decimal("150.00"), "currency": "USD"})
        assert evaluator.evaluate(ast) is True

        evaluator = Evaluator({"amount": Decimal("150.00"), "currency": "EUR"})
        assert evaluator.evaluate(ast) is False

    def test_evaluate_logical_or(self):
        ast = parse_expression("amount > 100 or amount < 10")
        evaluator = Evaluator({"amount": Decimal("5.00")})
        assert evaluator.evaluate(ast) is True

        evaluator = Evaluator({"amount": Decimal("150.00")})
        assert evaluator.evaluate(ast) is True

        evaluator = Evaluator({"amount": Decimal("50.00")})
        assert evaluator.evaluate(ast) is False

    def test_evaluate_not(self):
        ast = parse_expression("not amount > 100")
        evaluator = Evaluator({"amount": Decimal("50.00")})
        assert evaluator.evaluate(ast) is True

    def test_evaluate_parentheses(self):
        ast = parse_expression("(amount > 100) and (currency == 'USD')")
        evaluator = Evaluator({"amount": Decimal("150.00"), "currency": "USD"})
        assert evaluator.evaluate(ast) is True

    def test_evaluate_is_none(self):
        ast = parse_expression("device_risk_score is None")
        evaluator = Evaluator({"device_risk_score": None})
        assert evaluator.evaluate(ast) is True

        evaluator = Evaluator({"device_risk_score": 0.5})
        assert evaluator.evaluate(ast) is False

    def test_evaluate_is_not_none(self):
        ast = parse_expression("device_risk_score is not None")
        evaluator = Evaluator({"device_risk_score": 0.5})
        assert evaluator.evaluate(ast) is True

        evaluator = Evaluator({"device_risk_score": None})
        assert evaluator.evaluate(ast) is False

    def test_evaluate_unknown_variable_raises(self):
        ast = parse_expression("unknown_var > 100")
        evaluator = Evaluator({})
        with pytest.raises(ValueError, match="Unknown variable"):
            evaluator.evaluate(ast)


class TestEvaluateExpression:
    def test_basic_comparison(self):
        assert evaluate_expression("amount > 100", {"amount": Decimal("150")}) is True
        assert evaluate_expression("amount > 100", {"amount": Decimal("50")}) is False

    def test_string_comparison(self):
        assert evaluate_expression("currency == 'USD'", {"currency": "USD"}) is True
        assert evaluate_expression("currency == 'USD'", {"currency": "EUR"}) is False

    def test_logical_and(self):
        assert evaluate_expression("amount > 100 and currency == 'USD'", {"amount": Decimal("150"), "currency": "USD"}) is True
        assert evaluate_expression("amount > 100 and currency == 'USD'", {"amount": Decimal("150"), "currency": "EUR"}) is False

    def test_logical_or(self):
        assert evaluate_expression("amount > 100 or amount < 10", {"amount": Decimal("5")}) is True
        assert evaluate_expression("amount > 100 or amount < 10", {"amount": Decimal("150")}) is True
        assert evaluate_expression("amount > 100 or amount < 10", {"amount": Decimal("50")}) is False

    def test_logical_not(self):
        assert evaluate_expression("not amount > 100", {"amount": Decimal("50")}) is True
        assert evaluate_expression("not amount > 100", {"amount": Decimal("150")}) is False

    def test_parentheses(self):
        assert evaluate_expression("(amount > 100) and (currency == 'USD')", {"amount": Decimal("150"), "currency": "USD"}) is True

    def test_is_none(self):
        assert evaluate_expression("device_risk_score is None", {"device_risk_score": None}) is True
        assert evaluate_expression("device_risk_score is None", {"device_risk_score": 0.5}) is False

    def test_is_not_none(self):
        assert evaluate_expression("device_risk_score is not None", {"device_risk_score": 0.5}) is True
        assert evaluate_expression("device_risk_score is not None", {"device_risk_score": None}) is False

    def test_precedence(self):
        assert evaluate_expression("amount > 100 or amount < 10 and currency == 'USD'", {"amount": Decimal("5"), "currency": "USD"}) is True
        assert evaluate_expression("amount > 100 or amount < 10 and currency == 'USD'", {"amount": Decimal("150"), "currency": "EUR"}) is True
        assert evaluate_expression("amount > 100 or amount < 10 and currency == 'USD'", {"amount": Decimal("50"), "currency": "EUR"}) is False

    def test_missing_variable_returns_false(self):
        assert evaluate_expression("unknown > 100", {}) is False

    def test_malformed_expression_returns_false(self):
        assert evaluate_expression("amount >", {"amount": 100}) is False
        assert evaluate_expression("amount = 100", {"amount": 100}) is False
        assert evaluate_expression("import os; os.system('ls')", {}) is False


class TestSecurityRejection:
    def test_rejects_arbitrary_code_execution(self):
        malicious = [
            "__import__('os').system('ls')",
            "eval('1+1')",
            "exec('print(1)')",
            "open('/etc/passwd').read()",
            "os.system('ls')",
            "subprocess.run(['ls'])",
            "getattr(__builtins__, 'eval')('1+1')",
            "().__class__.__bases__[0].__subclasses__()",
            "globals()",
            "locals()",
            "vars()",
        ]
        for expr in malicious:
            assert evaluate_expression(expr, {}) is False, f"Should reject: {expr}"

    def test_rejects_builtin_access(self):
        assert evaluate_expression("__builtins__", {}) is False
        assert evaluate_expression("__builtins__.eval", {}) is False

    def test_rejects_attribute_access(self):
        assert evaluate_expression("amount.__class__", {"amount": 100}) is False
        assert evaluate_expression("amount.__dict__", {"amount": 100}) is False

    def test_rejects_function_calls(self):
        assert evaluate_expression("print(1)", {}) is False
        assert evaluate_expression("len(amount)", {"amount": "100"}) is False

    def test_rejects_method_calls(self):
        assert evaluate_expression("currency.upper()", {"currency": "USD"}) is False

    def test_rejects_slicing_indexing(self):
        assert evaluate_expression("currency[0]", {"currency": "USD"}) is False

    def test_rejects_comprehensions(self):
        assert evaluate_expression("[x for x in range(10)]", {}) is False


def make_rule(name: str, expression: str, action: TransactionAction, priority: int = 0, enabled: bool = True) -> Rule:
    return Rule(
        id=uuid4(),
        name=name,
        dsl_expression=expression,
        action=action,
        priority=priority,
        enabled=enabled,
        version=1,
    )


class TestRuleEngineWithNewParser:
    def test_basic_rules_still_work(self):
        rules = [
            make_rule("block_large", "amount > 10000", TransactionAction.BLOCK, priority=100),
            make_rule("review_medium", "amount > 1000", TransactionAction.REVIEW, priority=50),
            make_rule("allow_small", "amount < 100", TransactionAction.ALLOW, priority=10),
        ]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("50")})
        assert result.final_action == TransactionAction.ALLOW
        assert len(result.triggered_rules) == 1
        assert result.triggered_rules[0].rule_name == "allow_small"

        result = engine.evaluate({"amount": Decimal("5000")})
        assert result.final_action == TransactionAction.REVIEW
        assert len(result.triggered_rules) == 1
        assert result.triggered_rules[0].rule_name == "review_medium"

        result = engine.evaluate({"amount": Decimal("15000")})
        assert result.final_action == TransactionAction.BLOCK
        assert len(result.triggered_rules) >= 1

    def test_precedence_block_over_review(self):
        rules = [
            make_rule("block", "amount > 10000", TransactionAction.BLOCK, priority=100),
            make_rule("review", "amount > 100", TransactionAction.REVIEW, priority=50),
        ]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("15000")})
        assert result.final_action == TransactionAction.BLOCK
        assert len(result.triggered_rules) == 2

    def test_customer_risk_tier(self):
        rules = [make_rule("high_risk", "customer_risk_tier == 'high'", TransactionAction.BLOCK, priority=100)]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("100"), "customer_risk_tier": "high"})
        assert result.final_action == TransactionAction.BLOCK

        result = engine.evaluate({"amount": Decimal("100"), "customer_risk_tier": "standard"})
        assert result.final_action == TransactionAction.ALLOW

    def test_device_risk_score(self):
        rules = [make_rule("risky_device", "device_risk_score is not None and device_risk_score > 0.7", TransactionAction.REVIEW, priority=100)]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("100"), "device_risk_score": 0.8})
        assert result.final_action == TransactionAction.REVIEW

        result = engine.evaluate({"amount": Decimal("100"), "device_risk_score": 0.5})
        assert result.final_action == TransactionAction.ALLOW

        result = engine.evaluate({"amount": Decimal("100")})
        assert result.final_action == TransactionAction.ALLOW

    def test_merchant_category(self):
        rules = [make_rule("gambling", "merchant_category_code == '7995'", TransactionAction.BLOCK, priority=100)]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("100"), "merchant_category_code": "7995"})
        assert result.final_action == TransactionAction.BLOCK

    def test_risk_score_bounded(self):
        rules = [make_rule("block", "amount > 100", TransactionAction.BLOCK, priority=100)]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("1000000")})
        assert 0.0 <= result.risk_score <= 100.0

    def test_risk_score_zero_when_no_rules_triggered(self):
        rules = [make_rule("allow", "amount < 100", TransactionAction.ALLOW, priority=10)]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("200")})
        assert result.risk_score == 0.0

    def test_malicious_expressions_rejected(self):
        rules = [
            make_rule("malicious1", "__import__('os').system('ls')", TransactionAction.BLOCK, priority=100),
            make_rule("malicious2", "eval('1+1')", TransactionAction.BLOCK, priority=100),
            make_rule("malicious3", "open('/etc/passwd')", TransactionAction.BLOCK, priority=100),
            make_rule("malicious4", "currency.__class__", TransactionAction.BLOCK, priority=100),
        ]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("100"), "currency": "USD"})
        assert result.final_action == TransactionAction.ALLOW
        assert len(result.triggered_rules) == 0

    def test_attribute_access_rejected(self):
        rules = [make_rule("attr", "currency.__class__", TransactionAction.BLOCK, priority=100)]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("100"), "currency": "USD"})
        assert result.final_action == TransactionAction.ALLOW

    def test_function_calls_rejected(self):
        rules = [make_rule("func", "currency.upper()", TransactionAction.BLOCK, priority=100)]
        engine = RuleEngine(rules)

        result = engine.evaluate({"amount": Decimal("100"), "currency": "USD"})
        assert result.final_action == TransactionAction.ALLOW