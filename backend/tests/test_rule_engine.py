from __future__ import annotations

from decimal import Decimal
from uuid import uuid4


from app.services.rule_engine import RuleEngine, Rule, TransactionAction


def make_rule(
    name: str,
    expression: str,
    action: TransactionAction,
    priority: int = 0,
    enabled: bool = True,
) -> Rule:
    return Rule(
        id=uuid4(),
        name=name,
        dsl_expression=expression,
        action=action,
        priority=priority,
        enabled=enabled,
        version=1,
    )


class TestRuleEngineBasic:
    def test_no_rules_returns_allow(self):
        engine = RuleEngine([])
        result = engine.evaluate({"amount": Decimal("100")})
        assert result.final_action == TransactionAction.ALLOW
        assert result.triggered_rules == []
        assert result.risk_score == 0.0

    def test_single_block_rule(self):
        rule = make_rule("block_large", "amount > 1000", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("1500")})
        assert result.final_action == TransactionAction.BLOCK
        assert len(result.triggered_rules) == 1
        assert result.triggered_rules[0].rule_name == "block_large"

        result = engine.evaluate({"amount": Decimal("500")})
        assert result.final_action == TransactionAction.ALLOW
        assert len(result.triggered_rules) == 0
        assert result.risk_score == 0.0

    def test_single_review_rule(self):
        rule = make_rule("review_medium", "amount > 500", TransactionAction.REVIEW, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("600")})
        assert result.final_action == TransactionAction.REVIEW
        assert len(result.triggered_rules) == 1

        result = engine.evaluate({"amount": Decimal("400")})
        assert result.final_action == TransactionAction.ALLOW
        assert len(result.triggered_rules) == 0
        assert result.risk_score == 0.0

    def test_single_allow_rule(self):
        rule = make_rule("allow_small", "amount < 100", TransactionAction.ALLOW, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("50")})
        assert result.final_action == TransactionAction.ALLOW
        assert len(result.triggered_rules) == 1
        assert result.risk_score > 0.0
        assert result.risk_score <= 100.0

        result = engine.evaluate({"amount": Decimal("200")})
        assert result.final_action == TransactionAction.ALLOW
        assert len(result.triggered_rules) == 0
        assert result.risk_score == 0.0


class TestRuleEnginePrecedence:
    def test_block_overrides_review(self):
        block_rule = make_rule("block", "amount > 1000", TransactionAction.BLOCK, priority=10)
        review_rule = make_rule("review", "amount > 100", TransactionAction.REVIEW, priority=5)
        engine = RuleEngine([block_rule, review_rule])

        result = engine.evaluate({"amount": Decimal("1500")})
        assert result.final_action == TransactionAction.BLOCK
        assert len(result.triggered_rules) == 2
        rule_names = {r.rule_name for r in result.triggered_rules}
        assert rule_names == {"block", "review"}

    def test_review_overrides_allow(self):
        review_rule = make_rule("review", "amount > 100", TransactionAction.REVIEW, priority=10)
        allow_rule = make_rule("allow", "amount < 5000", TransactionAction.ALLOW, priority=5)
        engine = RuleEngine([review_rule, allow_rule])

        result = engine.evaluate({"amount": Decimal("500")})
        assert result.final_action == TransactionAction.REVIEW
        assert len(result.triggered_rules) == 2

    def test_multiple_block_rules_highest_priority(self):
        block1 = make_rule("block1", "amount > 1000", TransactionAction.BLOCK, priority=10)
        block2 = make_rule("block2", "currency == 'USD'", TransactionAction.BLOCK, priority=5)
        engine = RuleEngine([block1, block2])

        result = engine.evaluate({"amount": Decimal("1500"), "currency": "USD"})
        assert result.final_action == TransactionAction.BLOCK
        assert len(result.triggered_rules) == 2


class TestRuleEnginePriority:
    def test_rules_evaluated_in_priority_order(self):
        rule_low = make_rule("low", "amount > 100", TransactionAction.REVIEW, priority=1)
        rule_high = make_rule("high", "amount > 1000", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule_low, rule_high])

        result = engine.evaluate({"amount": Decimal("500")})
        assert result.final_action == TransactionAction.REVIEW
        assert len(result.triggered_rules) == 1
        assert result.triggered_rules[0].rule_name == "low"

        result = engine.evaluate({"amount": Decimal("1500")})
        assert result.final_action == TransactionAction.BLOCK
        assert len(result.triggered_rules) == 2


class TestRuleEngineDisabledRules:
    def test_disabled_rules_skipped(self):
        enabled = make_rule("enabled", "amount > 100", TransactionAction.REVIEW, priority=10)
        disabled = make_rule("disabled", "amount > 100", TransactionAction.BLOCK, priority=5, enabled=False)
        engine = RuleEngine([enabled, disabled])

        result = engine.evaluate({"amount": Decimal("500")})
        assert result.final_action == TransactionAction.REVIEW
        assert len(result.triggered_rules) == 1
        assert result.triggered_rules[0].rule_name == "enabled"


class TestRuleEngineComplexExpressions:
    def test_currency_check(self):
        rule = make_rule("usd_only", "currency == 'USD'", TransactionAction.REVIEW, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("100"), "currency": "USD"})
        assert result.final_action == TransactionAction.REVIEW

        result = engine.evaluate({"amount": Decimal("100"), "currency": "EUR"})
        assert result.final_action == TransactionAction.ALLOW

    def test_customer_risk_tier(self):
        rule = make_rule("high_risk_customer", "customer_risk_tier == 'high'", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("100"), "customer_risk_tier": "high"})
        assert result.final_action == TransactionAction.BLOCK

        result = engine.evaluate({"amount": Decimal("100"), "customer_risk_tier": "standard"})
        assert result.final_action == TransactionAction.ALLOW

    def test_device_risk_score(self):
        rule = make_rule("risky_device", "device_risk_score is not None and device_risk_score > 0.7", TransactionAction.REVIEW, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("100"), "device_risk_score": 0.8})
        assert result.final_action == TransactionAction.REVIEW

        result = engine.evaluate({"amount": Decimal("100"), "device_risk_score": 0.5})
        assert result.final_action == TransactionAction.ALLOW

        result = engine.evaluate({"amount": Decimal("100")})
        assert result.final_action == TransactionAction.ALLOW

    def test_merchant_category(self):
        rule = make_rule("gambling", "merchant_category_code == '7995'", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("100"), "merchant_category_code": "7995"})
        assert result.final_action == TransactionAction.BLOCK

        result = engine.evaluate({"amount": Decimal("100"), "merchant_category_code": "5411"})
        assert result.final_action == TransactionAction.ALLOW


class TestRuleEngineRiskScore:
    def test_risk_score_zero_for_no_triggered_rules(self):
        rule = make_rule("allow", "amount < 100", TransactionAction.ALLOW, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("200")})
        assert result.risk_score == 0.0

    def test_risk_score_positive_for_triggered_allow(self):
        rule = make_rule("allow", "amount < 100", TransactionAction.ALLOW, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("50")})
        assert result.risk_score > 0.0
        assert result.risk_score <= 100.0

    def test_risk_score_positive_for_review(self):
        rule = make_rule("review", "amount > 100", TransactionAction.REVIEW, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("500")})
        assert result.risk_score > 0.0
        assert result.risk_score <= 100.0

    def test_risk_score_higher_for_block(self):
        block_rule = make_rule("block", "amount > 1000", TransactionAction.BLOCK, priority=10)
        review_rule = make_rule("review", "amount > 100", TransactionAction.REVIEW, priority=5)
        engine = RuleEngine([block_rule, review_rule])

        result = engine.evaluate({"amount": Decimal("1500")})
        assert result.risk_score > 33.0

    def test_risk_score_bounded(self):
        rule = make_rule("block", "amount > 100", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("1000000")})
        assert 0.0 <= result.risk_score <= 100.0

    def test_risk_score_includes_amount_factor(self):
        rule = make_rule("block", "amount > 100", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result_small = engine.evaluate({"amount": Decimal("200")})
        result_large = engine.evaluate({"amount": Decimal("5000")})

        assert result_large.risk_score > result_small.risk_score

    def test_risk_score_includes_customer_risk(self):
        rule = make_rule("block", "amount > 100", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result_standard = engine.evaluate({"amount": Decimal("500"), "customer_risk_tier": "standard"})
        result_high = engine.evaluate({"amount": Decimal("500"), "customer_risk_tier": "high"})

        assert result_high.risk_score > result_standard.risk_score

    def test_risk_score_includes_device_risk(self):
        rule = make_rule("block", "amount > 100", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result_no_device = engine.evaluate({"amount": Decimal("500")})
        result_risky_device = engine.evaluate({"amount": Decimal("500"), "device_risk_score": 0.9})

        assert result_risky_device.risk_score > result_no_device.risk_score

    def test_risk_score_includes_merchant_risk(self):
        rule = make_rule("block", "amount > 100", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result_standard = engine.evaluate({"amount": Decimal("500"), "merchant_risk_level": "standard"})
        result_high = engine.evaluate({"amount": Decimal("500"), "merchant_risk_level": "high"})

        assert result_high.risk_score > result_standard.risk_score


class TestRuleEngineMalformedExpressions:
    def test_invalid_expression_returns_false(self):
        rule = make_rule("bad", "amount > ", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("500")})
        assert result.final_action == TransactionAction.ALLOW
        assert len(result.triggered_rules) == 0

    def test_missing_variable_returns_false(self):
        rule = make_rule("missing", "nonexistent > 100", TransactionAction.BLOCK, priority=10)
        engine = RuleEngine([rule])

        result = engine.evaluate({"amount": Decimal("500")})
        assert result.final_action == TransactionAction.ALLOW