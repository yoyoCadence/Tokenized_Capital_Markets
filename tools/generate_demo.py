"""Create the deterministic synthetic fixture; refuses to change existing history."""
from datetime import date, timedelta
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data/observed/demo.yaml"


def year_before(d):
    return d.replace(year=d.year - 1)


def build():
    observations = []
    ends = [date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]
    revenue = [90000000, 94000000, 97000000, 100000000]
    for index, end in enumerate(ends):
        prior = year_before(end)
        quarter_start = date(end.year, 3 * ((end.month - 1) // 3) + 1, 1)
        periods = {
            "SPOT": {"basis": "SPOT", "start": end.isoformat(), "end": end.isoformat()},
            "PRIOR_SPOT": {"basis": "SPOT", "start": prior.isoformat(), "end": prior.isoformat()},
            "TTM": {"basis": "TTM", "start": (prior + timedelta(days=1)).isoformat(), "end": end.isoformat()},
            "PRIOR_TTM": {"basis": "TTM", "start": (year_before(prior) + timedelta(days=1)).isoformat(), "end": prior.isoformat()},
            "QUARTER": {"basis": "QUARTER", "start": quarter_start.isoformat(), "end": end.isoformat()},
        }
        def add(metric, value, unit, period):
            observations.append({
                "id": f"demo_{end.isoformat()}_{metric}", "metric_id": metric,
                "classification": "OBSERVED", "value": value, "unit": unit,
                "source_id": "demo_dataset_v1", "as_of_date": end.isoformat(),
                "period": periods[period].copy(), "fixture": True,
            })

        for metric, value, unit, period in [
            ("tokenized_equity_aum", 2500000000 + index * 200000000, "USD", "SPOT"),
            ("tokenized_equity_volume", 1200000000 + index * 200000000, "USD", "TTM"),
            ("global_equity_market", 120000000000000, "USD", "SPOT"),
            ("uni_price", 9, "USD_PER_UNI", "SPOT"),
            ("uni_market_cap", [5900000000, 5950000000, 6000000000, 6050000000][index], "USD", "SPOT"),
            ("uni_fdv", 7100000000, "USD", "SPOT"),
            ("crypto_protocol_fees", 160000000, "USD", "TTM"),
            ("uni_net_supply_change", -1000000, "UNI", "QUARTER"),
            ("uni_protocol_activity_growth", 0.20, "FRACTION", "QUARTER"),
            ("secz_prior_revenue", 80000000, "USD", "PRIOR_TTM"),
            ("secz_aum", 10000000000, "USD", "SPOT"),
            ("secz_prior_aum", 8000000000, "USD", "PRIOR_SPOT"),
            ("secz_volume", 3000000000, "USD", "TTM"),
            ("secz_prior_volume", 2000000000, "USD", "PRIOR_TTM"),
            ("secz_ebitda", 15000000, "USD", "TTM"),
            ("secz_prior_ebitda", 10000000, "USD", "PRIOR_TTM"),
            ("secz_ev", 2000000000, "USD", "SPOT"),
            ("secz_price", 10, "USD", "SPOT"),
            ("secz_market_cap", 1900000000, "USD", "SPOT"),
            ("secz_fdv", 2000000000, "USD", "SPOT"),
            ("xlm_rwa_value", 1000000000, "USD", "SPOT"),
            ("xlm_prior_rwa_value", 800000000, "USD", "PRIOR_SPOT"),
            ("xlm_institutional_assets", 600000000, "USD", "SPOT"),
            ("xlm_prior_institutional_assets", 400000000, "USD", "PRIOR_SPOT"),
            ("xlm_stablecoin_supply", 4000000000, "USD", "SPOT"),
            ("xlm_stablecoin_transfer_volume", 6000000000, "USD", "TTM"),
            ("xlm_active_addresses", 120000, "COUNT", "SPOT"),
            ("xlm_institutional_issuers", 28, "COUNT", "SPOT"),
            ("xlm_transfer_volume", 12000000000, "USD", "TTM"),
            ("xlm_prior_transfer_volume", 10000000000, "USD", "PRIOR_TTM"),
            ("xlm_operations", 1000000000, "COUNT", "TTM"),
            ("xlm_average_fee", 0.00001, "XLM", "TTM"),
            ("xlm_price", 0.2, "USD_PER_XLM", "SPOT"),
            ("xlm_market_cap", 5000000000, "USD", "SPOT"),
            ("xlm_fdv", 10000000000, "USD", "SPOT"),
            ("xlm_account_reserve", 150000000, "XLM", "SPOT"),
            ("xlm_liquidity_demand", 200000000, "XLM", "SPOT"),
            ("xlm_collateral_demand", 40000000, "XLM", "SPOT"),
            ("xlm_settlement_demand", 100000000, "XLM", "SPOT"),
            ("xlm_other_locked", 10000000, "XLM", "SPOT"),
            ("xlm_prior_locked_demand", 490000000, "XLM", "PRIOR_SPOT"),
        ]:
            add(metric, value, unit, period)
        splits = [0.2, 0.25, 0.3, 0.1, 0.1, 0.05]
        for metric, weight in zip(("secz_tokenization_revenue", "secz_servicing_revenue", "secz_transaction_revenue", "secz_issuer_saas_revenue", "secz_fund_admin_revenue", "secz_other_revenue"), splits):
            add(metric, int(revenue[index] * weight), "USD", "TTM")
    return {"observations": observations}


if __name__ == "__main__":
    desired = yaml.safe_dump(build(), sort_keys=False, allow_unicode=True)
    if TARGET.exists() and TARGET.read_text(encoding="utf-8") != desired:
        raise SystemExit("Refusing to overwrite a changed demo ledger")
    TARGET.write_text(desired, encoding="utf-8")
    print(f"{len(build()['observations'])} DEMO observations in {TARGET}")
