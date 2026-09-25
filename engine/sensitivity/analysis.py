from engine.formulas.runtime import calculate
from engine.thesis.rules import evaluate_theses


def run(project, overrides, as_of=None):
    current = calculate(project, as_of, overrides)
    current["thesis"] = evaluate_theses(project, current, overrides)
    current["overrides"] = overrides
    return current


def matrix(project, as_of=None, fees=(0.5, 1, 1.25, 2, 3), turns=(0.5, 1, 2, 3, 4), overrides=None):
    return {"fee_bp": list(fees), "turnover": list(turns),
            "cells": [[calculate(project, as_of, {**(overrides or {}), "effective_protocol_fee_bp": fee, "turnover": turn})
                       ["metrics"]["required_uniswap_market_share"]["value"] for fee in fees] for turn in turns]}
