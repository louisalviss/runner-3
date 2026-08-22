"""
Wave Rider RS/RW research module.
Research only. No changes to canonical WR execution.
"""


def calculate_rsrw(asset_close, btc_close, ema_length=21):
    ratio = asset_close / btc_close
    # EMA calculation is injected by the backtest runner.
    # This module only defines the intended research interface.
    return ratio


def classify_rsrw(ratio, ratio_ema, slope_up=True, slope_down=True):
    rs = ratio > ratio_ema and slope_up
    rw = ratio < ratio_ema and slope_down
    return {"RS": rs, "RW": rw}
