#!/usr/bin/env python3
import trinity_backtest_bybit as adapter
adapter.tb.REPORT_DAYS = 30
adapter.tb.WARMUP_DAYS = 14
adapter.tb.main()
