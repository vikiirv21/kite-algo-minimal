# Repository Overview -- kite-algo-minimal

This document summarizes the repository layout, backend/frontend split, and runtime artifacts.

---

## 1. Repository Tree (top levels)

```text
kite-algo-minimal
├── .githooks
│   └── pre-commit
├── analytics
│   ├── __init__.py
│   ├── learning_engine.py
│   ├── multi_timeframe_engine.py
│   ├── multi_timeframe_scanner.py
│   ├── performance.py
│   ├── performance_utils.py
│   ├── strategy_performance.py
│   ├── trade_journal.py
│   ├── trade_recorder.py
│   └── trade_scorer.py
├── apps
│   ├── __init__.py
│   ├── dashboard.py
│   └── server.py
├── artifacts
│   ├── checkpoints
│   │   ├── paper_state_latest.json
│   │   └── runtime_state_latest.json
│   ├── history
│   │   ├── 2025-11-11
│   │   ├── 2025-11-12
│   │   ├── 2025-11-13
│   │   └── 2025-11-14
│   ├── journal
│   │   └── 2025-11-12
│   ├── logs
│   │   ├── engine_events.jsonl
│   │   └── events.jsonl
│   ├── replay_2025-11-07
│   │   ├── equity
│   │   ├── fno
│   │   └── options
│   ├── snapshots
│   │   ├── positions_20251112_182816.json
│   │   ├── positions_20251112_192834.json
│   │   ├── positions_20251112_192842.json
│   │   ├── positions_20251112_232625.json
│   │   ├── positions_20251112_232801.json
│   │   ├── positions_20251113_000133.json
│   │   ├── positions_20251113_001925.json
│   │   ├── positions_20251113_012553.json
│   │   ├── positions_20251113_091238.json
│   │   ├── positions_20251113_091247.json
│   │   ├── positions_20251113_091734.json
│   │   ├── positions_20251113_091835.json
│   │   ├── positions_20251113_120604.json
│   │   ├── positions_20251113_120824.json
│   │   ├── positions_20251113_121219.json
│   │   ├── positions_20251113_122446.json
│   │   ├── positions_20251113_122920.json
│   │   ├── positions_20251113_124431.json
│   │   ├── positions_20251113_183537.json
│   │   ├── positions_20251113_184431.json
│   │   ├── positions_20251113_185248.json
│   │   ├── positions_20251113_191941.json
│   │   ├── positions_20251113_194328.json
│   │   ├── positions_20251114_001526.json
│   │   ├── positions_20251114_001658.json
│   │   ├── positions_20251114_004826.json
│   │   ├── positions_20251114_010207.json
│   │   ├── positions_20251114_010448.json
│   │   ├── positions_20251114_012848.json
│   │   ├── positions_20251114_033639.json
│   │   ├── positions_20251114_033700.json
│   │   ├── positions_20251114_090721.json
│   │   ├── positions_20251114_091221.json
│   │   ├── positions_20251114_114138.json
│   │   ├── positions_20251114_114223.json
│   │   ├── positions_20251114_114250.json
│   │   ├── positions_20251114_114316.json
│   │   ├── positions_20251114_114343.json
│   │   ├── positions_20251114_114409.json
│   │   ├── positions_20251114_114435.json
│   │   ├── positions_20251114_114501.json
│   │   ├── positions_20251114_114527.json
│   │   ├── positions_20251114_114555.json
│   │   ├── positions_20251114_114621.json
│   │   ├── positions_20251114_114647.json
│   │   ├── positions_20251114_114713.json
│   │   ├── positions_20251114_114739.json
│   │   ├── positions_20251114_114805.json
│   │   ├── positions_20251114_114832.json
│   │   ├── positions_20251114_114859.json
│   │   ├── positions_20251114_114924.json
│   │   ├── positions_20251114_114950.json
│   │   ├── positions_20251114_115016.json
│   │   ├── positions_20251114_115043.json
│   │   ├── positions_20251114_115109.json
│   │   ├── positions_20251114_115135.json
│   │   ├── positions_20251114_115201.json
│   │   ├── positions_20251114_115227.json
│   │   ├── positions_20251114_115253.json
│   │   ├── positions_20251114_115319.json
│   │   ├── positions_20251114_115345.json
│   │   ├── positions_20251114_115411.json
│   │   ├── positions_20251114_115437.json
│   │   ├── positions_20251114_115503.json
│   │   ├── positions_20251114_115529.json
│   │   ├── positions_20251114_115555.json
│   │   ├── positions_20251114_115621.json
│   │   ├── positions_20251114_115647.json
│   │   ├── positions_20251114_115713.json
│   │   ├── positions_20251114_115739.json
│   │   ├── positions_20251114_115805.json
│   │   ├── positions_20251114_115833.json
│   │   ├── positions_20251114_115859.json
│   │   ├── positions_20251114_115925.json
│   │   ├── positions_20251114_115951.json
│   │   ├── positions_20251114_120017.json
│   │   ├── positions_20251114_120043.json
│   │   ├── positions_20251114_120109.json
│   │   ├── positions_20251114_120135.json
│   │   ├── positions_20251114_120202.json
│   │   ├── positions_20251114_120228.json
│   │   ├── positions_20251114_120255.json
│   │   ├── positions_20251114_120321.json
│   │   ├── positions_20251114_120347.json
│   │   ├── positions_20251114_120414.json
│   │   ├── positions_20251114_120442.json
│   │   ├── positions_20251114_120508.json
│   │   ├── positions_20251114_120534.json
│   │   ├── positions_20251114_120602.json
│   │   ├── positions_20251114_120606.json
│   │   ├── positions_20251114_120610.json
│   │   ├── positions_20251114_120632.json
│   │   ├── positions_20251114_120658.json
│   │   ├── positions_20251114_120724.json
│   │   ├── positions_20251114_120750.json
│   │   ├── positions_20251114_120816.json
│   │   ├── positions_20251114_120843.json
│   │   ├── positions_20251114_120909.json
│   │   ├── positions_20251114_120935.json
│   │   ├── positions_20251114_121001.json
│   │   ├── positions_20251114_121027.json
│   │   ├── positions_20251114_121053.json
│   │   ├── positions_20251114_121119.json
│   │   ├── positions_20251114_121145.json
│   │   ├── positions_20251114_121211.json
│   │   ├── positions_20251114_121237.json
│   │   ├── positions_20251114_121303.json
│   │   ├── positions_20251114_121329.json
│   │   ├── positions_20251114_121354.json
│   │   ├── positions_20251114_121420.json
│   │   ├── positions_20251114_121447.json
│   │   ├── positions_20251114_121513.json
│   │   ├── positions_20251114_121539.json
│   │   ├── positions_20251114_121605.json
│   │   ├── positions_20251114_121631.json
│   │   ├── positions_20251114_121657.json
│   │   ├── positions_20251114_121723.json
│   │   ├── positions_20251114_121749.json
│   │   ├── positions_20251114_121815.json
│   │   ├── positions_20251114_121841.json
│   │   ├── positions_20251114_121908.json
│   │   ├── positions_20251114_121933.json
│   │   ├── positions_20251114_121959.json
│   │   ├── positions_20251114_122026.json
│   │   ├── positions_20251114_122052.json
│   │   ├── positions_20251114_122118.json
│   │   ├── positions_20251114_122144.json
│   │   ├── positions_20251114_122210.json
│   │   ├── positions_20251114_122236.json
│   │   ├── positions_20251114_122302.json
│   │   ├── positions_20251114_122328.json
│   │   ├── positions_20251114_122354.json
│   │   ├── positions_20251114_122420.json
│   │   ├── positions_20251114_122446.json
│   │   ├── positions_20251114_122513.json
│   │   ├── positions_20251114_122539.json
│   │   ├── positions_20251114_122605.json
│   │   ├── positions_20251114_122631.json
│   │   ├── positions_20251114_122657.json
│   │   ├── positions_20251114_122724.json
│   │   ├── positions_20251114_122750.json
│   │   ├── positions_20251114_122819.json
│   │   ├── positions_20251114_122846.json
│   │   ├── positions_20251114_122912.json
│   │   ├── positions_20251114_122939.json
│   │   ├── positions_20251114_123005.json
│   │   ├── positions_20251114_123031.json
│   │   ├── positions_20251114_123057.json
│   │   ├── positions_20251114_123124.json
│   │   ├── positions_20251114_123150.json
│   │   ├── positions_20251114_123216.json
│   │   ├── positions_20251114_123243.json
│   │   ├── positions_20251114_123310.json
│   │   ├── positions_20251114_123336.json
│   │   ├── positions_20251114_123403.json
│   │   ├── positions_20251114_123433.json
│   │   ├── positions_20251114_123502.json
│   │   ├── positions_20251114_123530.json
│   │   ├── positions_20251114_123557.json
│   │   ├── positions_20251114_123624.json
│   │   ├── positions_20251114_123650.json
│   │   ├── positions_20251114_123718.json
│   │   ├── positions_20251114_123744.json
│   │   ├── positions_20251114_123810.json
│   │   ├── positions_20251114_123844.json
│   │   ├── positions_20251114_123911.json
│   │   ├── positions_20251114_123936.json
│   │   ├── positions_20251114_124003.json
│   │   ├── positions_20251114_124030.json
│   │   ├── positions_20251114_124056.json
│   │   ├── positions_20251114_124123.json
│   │   ├── positions_20251114_124149.json
│   │   ├── positions_20251114_124216.json
│   │   ├── positions_20251114_124242.json
│   │   ├── positions_20251114_124309.json
│   │   ├── positions_20251114_124343.json
│   │   ├── positions_20251114_124410.json
│   │   ├── positions_20251114_124436.json
│   │   ├── positions_20251114_124502.json
│   │   ├── positions_20251114_124529.json
│   │   ├── positions_20251114_124556.json
│   │   ├── positions_20251114_124622.json
│   │   ├── positions_20251114_124656.json
│   │   ├── positions_20251114_124722.json
│   │   ├── positions_20251114_124749.json
│   │   ├── positions_20251114_124817.json
│   │   ├── positions_20251114_124844.json
│   │   ├── positions_20251114_124910.json
│   │   ├── positions_20251114_124937.json
│   │   ├── positions_20251114_125006.json
│   │   ├── positions_20251114_125033.json
│   │   ├── positions_20251114_125059.json
│   │   ├── positions_20251114_125129.json
│   │   ├── positions_20251114_125155.json
│   │   ├── positions_20251114_125221.json
│   │   ├── positions_20251114_125251.json
│   │   ├── positions_20251114_125319.json
│   │   ├── positions_20251114_125345.json
│   │   ├── positions_20251114_125411.json
│   │   ├── positions_20251114_125444.json
│   │   ├── positions_20251114_125510.json
│   │   ├── positions_20251114_125536.json
│   │   ├── positions_20251114_125605.json
│   │   ├── positions_20251114_125631.json
│   │   ├── positions_20251114_125657.json
│   │   ├── positions_20251114_125725.json
│   │   ├── positions_20251114_125755.json
│   │   ├── positions_20251114_125821.json
│   │   ├── positions_20251114_125848.json
│   │   ├── positions_20251114_125921.json
│   │   ├── positions_20251114_125947.json
│   │   ├── positions_20251114_130013.json
│   │   ├── positions_20251114_130040.json
│   │   ├── positions_20251114_130109.json
│   │   ├── positions_20251114_130135.json
│   │   ├── positions_20251114_130153.json
│   │   ├── positions_20251114_130157.json
│   │   ├── positions_20251114_130218.json
│   │   ├── positions_20251114_130244.json
│   │   ├── positions_20251114_130310.json
│   │   ├── positions_20251114_130336.json
│   │   ├── positions_20251114_130402.json
│   │   ├── positions_20251114_130428.json
│   │   ├── positions_20251114_130454.json
│   │   ├── positions_20251114_130520.json
│   │   ├── positions_20251114_130546.json
│   │   ├── positions_20251114_130612.json
│   │   ├── positions_20251114_130638.json
│   │   ├── positions_20251114_130704.json
│   │   ├── positions_20251114_130730.json
│   │   ├── positions_20251114_130756.json
│   │   ├── positions_20251114_130822.json
│   │   ├── positions_20251114_130849.json
│   │   ├── positions_20251114_130915.json
│   │   ├── positions_20251114_130940.json
│   │   ├── positions_20251114_131007.json
│   │   ├── positions_20251114_131032.json
│   │   ├── positions_20251114_131058.json
│   │   ├── positions_20251114_131124.json
│   │   ├── positions_20251114_131150.json
│   │   ├── positions_20251114_131216.json
│   │   ├── positions_20251114_131242.json
│   │   ├── positions_20251114_131308.json
│   │   ├── positions_20251114_131334.json
│   │   ├── positions_20251114_131400.json
│   │   ├── positions_20251114_131426.json
│   │   ├── positions_20251114_131452.json
│   │   ├── positions_20251114_131518.json
│   │   ├── positions_20251114_131544.json
│   │   ├── positions_20251114_131610.json
│   │   ├── positions_20251114_131636.json
│   │   ├── positions_20251114_131701.json
│   │   ├── positions_20251114_131727.json
│   │   ├── positions_20251114_131754.json
│   │   ├── positions_20251114_131809.json
│   │   ├── positions_20251114_131812.json
│   │   ├── positions_20251114_131835.json
│   │   ├── positions_20251114_131900.json
│   │   ├── positions_20251114_131926.json
│   │   ├── positions_20251114_131952.json
│   │   ├── positions_20251114_132018.json
│   │   ├── positions_20251114_132044.json
│   │   ├── positions_20251114_132110.json
│   │   ├── positions_20251114_132136.json
│   │   ├── positions_20251114_132203.json
│   │   ├── positions_20251114_132228.json
│   │   ├── positions_20251114_132255.json
│   │   ├── positions_20251114_132321.json
│   │   ├── positions_20251114_132346.json
│   │   ├── positions_20251114_132412.json
│   │   ├── positions_20251114_132439.json
│   │   ├── positions_20251114_132505.json
│   │   ├── positions_20251114_132531.json
│   │   ├── positions_20251114_132556.json
│   │   ├── positions_20251114_132623.json
│   │   ├── positions_20251114_132649.json
│   │   ├── positions_20251114_132715.json
│   │   ├── positions_20251114_132742.json
│   │   ├── positions_20251114_132807.json
│   │   ├── positions_20251114_132833.json
│   │   ├── positions_20251114_132859.json
│   │   ├── positions_20251114_132926.json
│   │   ├── positions_20251114_132952.json
│   │   ├── positions_20251114_133017.json
│   │   ├── positions_20251114_133044.json
│   │   ├── positions_20251114_133110.json
│   │   ├── positions_20251114_133136.json
│   │   ├── positions_20251114_133201.json
│   │   ├── positions_20251114_133228.json
│   │   ├── positions_20251114_133254.json
│   │   ├── positions_20251114_133319.json
│   │   ├── positions_20251114_133345.json
│   │   ├── positions_20251114_133412.json
│   │   ├── positions_20251114_133438.json
│   │   ├── positions_20251114_133504.json
│   │   ├── positions_20251114_133530.json
│   │   ├── positions_20251114_133556.json
│   │   ├── positions_20251114_133622.json
│   │   ├── positions_20251114_133648.json
│   │   ├── positions_20251114_133715.json
│   │   ├── positions_20251114_133741.json
│   │   ├── positions_20251114_133807.json
│   │   ├── positions_20251114_133833.json
│   │   ├── positions_20251114_133900.json
│   │   ├── positions_20251114_133927.json
│   │   ├── positions_20251114_133953.json
│   │   ├── positions_20251114_134019.json
│   │   ├── positions_20251114_134045.json
│   │   ├── positions_20251114_134112.json
│   │   ├── positions_20251114_134140.json
│   │   ├── positions_20251114_134215.json
│   │   ├── positions_20251114_134246.json
│   │   ├── positions_20251114_134314.json
│   │   ├── positions_20251114_134340.json
│   │   ├── positions_20251114_134406.json
│   │   ├── positions_20251114_134433.json
│   │   ├── positions_20251114_134500.json
│   │   ├── positions_20251114_134527.json
│   │   ├── positions_20251114_134553.json
│   │   ├── positions_20251114_134619.json
│   │   ├── positions_20251114_134647.json
│   │   ├── positions_20251114_134713.json
│   │   ├── positions_20251114_134739.json
│   │   ├── positions_20251114_134805.json
│   │   ├── positions_20251114_134833.json
│   │   ├── positions_20251114_134900.json
│   │   ├── positions_20251114_134927.json
│   │   ├── positions_20251114_134953.json
│   │   ├── positions_20251114_135023.json
│   │   ├── positions_20251114_135050.json
│   │   ├── positions_20251114_135116.json
│   │   ├── positions_20251114_135142.json
│   │   ├── positions_20251114_135208.json
│   │   ├── positions_20251114_135234.json
│   │   ├── positions_20251114_135301.json
│   │   ├── positions_20251114_135327.json
│   │   ├── positions_20251114_135353.json
│   │   ├── positions_20251114_135420.json
│   │   ├── positions_20251114_135447.json
│   │   ├── positions_20251114_135513.json
│   │   ├── positions_20251114_135539.json
│   │   ├── positions_20251114_135605.json
│   │   ├── positions_20251114_135635.json
│   │   ├── positions_20251114_135702.json
│   │   ├── positions_20251114_135728.json
│   │   ├── positions_20251114_135754.json
│   │   ├── positions_20251114_135820.json
│   │   ├── positions_20251114_135847.json
│   │   ├── positions_20251114_135916.json
│   │   ├── positions_20251114_135942.json
│   │   ├── positions_20251114_140008.json
│   │   ├── positions_20251114_140034.json
│   │   ├── positions_20251114_140103.json
│   │   ├── positions_20251114_140130.json
│   │   ├── positions_20251114_140156.json
│   │   ├── positions_20251114_140222.json
│   │   ├── positions_20251114_140248.json
│   │   ├── positions_20251114_140315.json
│   │   ├── positions_20251114_140342.json
│   │   ├── positions_20251114_140408.json
│   │   ├── positions_20251114_140434.json
│   │   ├── positions_20251114_140501.json
│   │   ├── positions_20251114_140527.json
│   │   ├── positions_20251114_140553.json
│   │   ├── positions_20251114_140619.json
│   │   ├── positions_20251114_140646.json
│   │   ├── positions_20251114_140712.json
│   │   ├── positions_20251114_140742.json
│   │   ├── positions_20251114_140808.json
│   │   ├── positions_20251114_140835.json
│   │   ├── positions_20251114_140902.json
│   │   ├── positions_20251114_140928.json
│   │   ├── positions_20251114_140955.json
│   │   ├── positions_20251114_141021.json
│   │   ├── positions_20251114_141048.json
│   │   ├── positions_20251114_141114.json
│   │   ├── positions_20251114_141141.json
│   │   ├── positions_20251114_141207.json
│   │   ├── positions_20251114_141233.json
│   │   ├── positions_20251114_141302.json
│   │   ├── positions_20251114_141329.json
│   │   ├── positions_20251114_141355.json
│   │   ├── positions_20251114_141422.json
│   │   ├── positions_20251114_141451.json
│   │   ├── positions_20251114_141517.json
│   │   ├── positions_20251114_141544.json
│   │   ├── positions_20251114_141610.json
│   │   ├── positions_20251114_141637.json
│   │   ├── positions_20251114_141744.json
│   │   ├── positions_20251114_141812.json
│   │   ├── positions_20251114_141839.json
│   │   ├── positions_20251114_141946.json
│   │   ├── positions_20251114_142013.json
│   │   ├── positions_20251114_142040.json
│   │   ├── positions_20251114_142121.json
│   │   ├── positions_20251114_142151.json
│   │   ├── positions_20251114_142219.json
│   │   ├── positions_20251114_142246.json
│   │   ├── positions_20251114_142314.json
│   │   ├── positions_20251114_142341.json
│   │   ├── positions_20251114_142408.json
│   │   ├── positions_20251114_142434.json
│   │   ├── positions_20251114_142501.json
│   │   ├── positions_20251114_142528.json
│   │   ├── positions_20251114_142557.json
│   │   ├── positions_20251114_142624.json
│   │   ├── positions_20251114_142650.json
│   │   ├── positions_20251114_142719.json
│   │   ├── positions_20251114_142746.json
│   │   ├── positions_20251114_142813.json
│   │   ├── positions_20251114_142840.json
│   │   ├── positions_20251114_142907.json
│   │   ├── positions_20251114_143007.json
│   │   ├── positions_20251114_143034.json
│   │   ├── positions_20251114_143101.json
│   │   ├── positions_20251114_143133.json
│   │   ├── positions_20251114_143200.json
│   │   ├── positions_20251114_143227.json
│   │   ├── positions_20251114_143256.json
│   │   ├── positions_20251114_143331.json
│   │   ├── positions_20251114_143814.json
│   │   ├── positions_20251114_143842.json
│   │   ├── positions_20251114_143908.json
│   │   ├── positions_20251114_144019.json
│   │   ├── positions_20251114_144045.json
│   │   ├── positions_20251114_144115.json
│   │   ├── positions_20251114_144146.json
│   │   ├── positions_20251114_144212.json
│   │   ├── positions_20251114_144309.json
│   │   ├── positions_20251114_144338.json
│   │   ├── positions_20251114_144410.json
│   │   ├── positions_20251114_144501.json
│   │   ├── positions_20251114_144530.json
│   │   ├── positions_20251114_144559.json
│   │   ├── positions_20251114_144806.json
│   │   ├── positions_20251114_144856.json
│   │   ├── positions_20251114_144906.json
│   │   ├── positions_20251114_144912.json
│   │   ├── positions_20251114_144920.json
│   │   ├── positions_20251114_144941.json
│   │   ├── positions_20251114_145040.json
│   │   ├── positions_20251114_145730.json
│   │   ├── positions_20251114_145740.json
│   │   ├── positions_20251114_145854.json
│   │   ├── positions_20251114_150124.json
│   │   ├── positions_20251114_150802.json
│   │   ├── positions_20251114_150824.json
│   │   ├── positions_20251114_150852.json
│   │   ├── positions_20251114_150918.json
│   │   ├── positions_20251114_150944.json
│   │   ├── positions_20251114_151010.json
│   │   ├── positions_20251114_151036.json
│   │   ├── positions_20251114_151102.json
│   │   ├── positions_20251114_151128.json
│   │   ├── positions_20251114_151154.json
│   │   ├── positions_20251114_151220.json
│   │   ├── positions_20251114_151246.json
│   │   ├── positions_20251114_151312.json
│   │   ├── positions_20251114_151338.json
│   │   ├── positions_20251114_151404.json
│   │   ├── positions_20251114_151430.json
│   │   ├── positions_20251114_151456.json
│   │   ├── positions_20251114_151522.json
│   │   ├── positions_20251114_151548.json
│   │   ├── positions_20251114_151614.json
│   │   ├── positions_20251114_151640.json
│   │   ├── positions_20251114_151706.json
│   │   ├── positions_20251114_151732.json
│   │   ├── positions_20251114_151759.json
│   │   ├── positions_20251114_151825.json
│   │   ├── positions_20251114_151852.json
│   │   ├── positions_20251114_151918.json
│   │   ├── positions_20251114_151944.json
│   │   ├── positions_20251114_152010.json
│   │   ├── positions_20251114_152036.json
│   │   ├── positions_20251114_152102.json
│   │   ├── positions_20251114_152128.json
│   │   ├── positions_20251114_152154.json
│   │   ├── positions_20251114_152220.json
│   │   ├── positions_20251114_152246.json
│   │   ├── positions_20251114_152312.json
│   │   ├── positions_20251114_152339.json
│   │   ├── positions_20251114_152405.json
│   │   ├── positions_20251114_152430.json
│   │   ├── positions_20251114_152456.json
│   │   ├── positions_20251114_152523.json
│   │   ├── positions_20251114_152549.json
│   │   ├── positions_20251114_152615.json
│   │   ├── positions_20251114_152642.json
│   │   ├── positions_20251114_152708.json
│   │   ├── positions_20251114_152734.json
│   │   ├── positions_20251114_152801.json
│   │   ├── positions_20251114_152828.json
│   │   ├── positions_20251114_152854.json
│   │   ├── positions_20251114_152920.json
│   │   ├── positions_20251114_152947.json
│   │   ├── positions_20251114_163718.json
│   │   ├── positions_20251114_163722.json
│   │   ├── positions_20251114_165302.json
│   │   ├── positions_20251114_165306.json
│   │   ├── positions_20251114_170949.json
│   │   ├── positions_20251114_170953.json
│   │   ├── positions_20251114_175733.json
│   │   └── positions_20251114_175737.json
│   ├── instrument_tokens.json
│   ├── live_quotes.json
│   ├── orders.csv
│   ├── paper_state.json
│   ├── runtime_mode.json
│   ├── signals.csv
│   └── snapshots.csv
├── auth
├── broker
│   ├── __init__.py
│   ├── auth.py
│   ├── execution_router.py
│   ├── kite_client.py
│   ├── live_broker.py
│   └── paper_broker.py
├── config
│   └── universe_equity.csv
├── configs
│   ├── dev.yaml
│   └── timeframes.py
├── core
│   ├── __init__.py
│   ├── atr_risk.py
│   ├── broker_sync.py
│   ├── config.py
│   ├── event_logging.py
│   ├── history_loader.py
│   ├── json_log.py
│   ├── kite_auth.py
│   ├── kite_env.py
│   ├── kite_http.py
│   ├── logging_utils.py
│   ├── market_session.py
│   ├── modes.py
│   ├── pattern_filters.py
│   ├── regime_detector.py
│   ├── risk_engine.py
│   ├── risk_engine_v2.py
│   ├── runtime_mode.py
│   ├── session.py
│   ├── signal_filters.py
│   ├── signal_quality.py
│   ├── state_store.py
│   ├── strategy_tags.py
│   ├── trade_monitor.py
│   ├── trade_throttler.py
│   ├── universe.py
│   └── universe_builder.py
├── data
│   ├── __init__.py
│   ├── broker_feed.py
│   ├── instruments.py
│   └── options_instruments.py
├── docs
│   ├── dashboard.md
│   └── repo_overview.md
├── engine
│   ├── __init__.py
│   ├── bootstrap.py
│   ├── equity_paper_engine.py
│   ├── meta_strategy_engine.py
│   ├── options_paper_engine.py
│   └── paper_engine.py
├── logs
│   ├── .gitkeep
│   ├── kite_algo_20251108.log
│   ├── kite_algo_20251109.log
│   ├── kite_algo_20251110.log
│   ├── kite_algo_20251111.log
│   ├── kite_algo_20251112.log
│   ├── kite_algo_20251113.log
│   └── kite_algo_20251114.log
├── risk
│   ├── adaptive_risk_manager.py
│   ├── cost_model.py
│   ├── factory.py
│   ├── position_sizer.py
│   └── trade_quality.py
├── scripts
│   ├── __init__.py
│   ├── analyze_and_learn.py
│   ├── analyze_paper_results.py
│   ├── analyze_performance.py
│   ├── analyze_strategy_performance.py
│   ├── backfill_history.py
│   ├── diag_kite_ws.py
│   ├── live_quotes.py
│   ├── login_kite.py
│   ├── replay_from_historical.py
│   ├── run_all.py
│   ├── run_dashboard.py
│   ├── run_day.py
│   ├── run_indicator_scanner.py
│   ├── run_learning_engine.py
│   ├── run_paper_equity.py
│   ├── run_paper_fno.py
│   ├── run_paper_options.py
│   └── show_paper_state.py
├── secrets
│   ├── kite.env
│   └── kite_tokens.env
├── static
│   ├── dashboard.css
│   └── dashboard.js
├── strategies
│   ├── __init__.py
│   ├── base.py
│   ├── equity_intraday_simple.py
│   ├── fno_intraday_trend.py
│   └── mean_reversion_intraday.py
├── templates
│   └── dashboard.html
├── tests
│   └── test_atr_risk.py
├── tools
│   ├── docs
│   │   └── repo_audit.py
│   └── docsync.py
├── ui
│   ├── static
│   │   ├── dashboard.css
│   │   └── dashboard.js
│   ├── templates
│   │   └── dashboard.html
│   ├── __init__.py
│   ├── dashboard.py
│   └── services.py
├── .env
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

---

## 2. Modules by Area

**Backend directories (inferred):**

`analytics`, `apps`, `broker`, `core`, `data`, `engine`, `scripts`

**Frontend/UI directories (inferred):**

`static`, `templates`, `ui`

**Shared/utility directories:**

`.githooks`, `artifacts`, `auth`, `config`, `configs`, `docs`, `logs`, `risk`, `secrets`, `strategies`, `tests`, `tools`

---

## 3. Backend <-> Frontend Wiring

### 3.1 FastAPI routes

| Method | Path | File |
| ------ | ---- | ---- |
| `GET` | `/` | `apps\dashboard.py` |
| `GET` | `/` | `ui\dashboard.py` |
| `POST` | `/admin/login` | `apps\server.py` |
| `POST` | `/admin/mode` | `apps\server.py` |
| `POST` | `/admin/resync` | `apps\server.py` |
| `POST` | `/admin/start` | `apps\server.py` |
| `POST` | `/admin/stop` | `apps\server.py` |
| `GET` | `/api/auth/status` | `ui\dashboard.py` |
| `GET` | `/api/config/summary` | `apps\dashboard.py` |
| `GET` | `/api/config/summary` | `ui\dashboard.py` |
| `GET` | `/api/debug/auth` | `ui\dashboard.py` |
| `GET` | `/api/engines/status` | `ui\dashboard.py` |
| `GET` | `/api/health` | `ui\dashboard.py` |
| `GET` | `/api/logs` | `ui\dashboard.py` |
| `GET` | `/api/logs/recent` | `ui\dashboard.py` |
| `GET` | `/api/margins` | `ui\dashboard.py` |
| `GET` | `/api/meta` | `apps\dashboard.py` |
| `GET` | `/api/meta` | `ui\dashboard.py` |
| `GET` | `/api/monitor/trade_flow` | `ui\dashboard.py` |
| `GET` | `/api/orders` | `ui\dashboard.py` |
| `GET` | `/api/orders/recent` | `ui\dashboard.py` |
| `GET` | `/api/pm/log` | `ui\dashboard.py` |
| `GET` | `/api/portfolio/summary` | `ui\dashboard.py` |
| `GET` | `/api/positions/open` | `ui\dashboard.py` |
| `GET` | `/api/positions_normalized` | `ui\dashboard.py` |
| `GET` | `/api/quality/summary` | `ui\dashboard.py` |
| `GET` | `/api/quotes` | `ui\dashboard.py` |
| `POST` | `/api/resync` | `ui\dashboard.py` |
| `GET` | `/api/signals` | `ui\dashboard.py` |
| `GET` | `/api/signals/recent` | `ui\dashboard.py` |
| `GET` | `/api/state` | `ui\dashboard.py` |
| `GET` | `/api/stats/equity` | `ui\dashboard.py` |
| `GET` | `/api/stats/strategies` | `ui\dashboard.py` |
| `GET` | `/api/strategy_performance` | `ui\dashboard.py` |
| `GET` | `/api/summary/today` | `ui\dashboard.py` |
| `GET` | `/api/system/time` | `ui\dashboard.py` |
| `GET` | `/api/trade_flow` | `ui\dashboard.py` |
| `GET` | `/healthz` | `apps\server.py` |

### 3.2 Frontend fetch() calls

These are the network calls from HTML/JS that hit your backend:

| Frontend File | Calls Path |
| ------------- | ---------- |
| `static\dashboard.js` | `/api/config/summary` |
| `static\dashboard.js` | `/api/engines/status` |
| `static\dashboard.js` | `/api/health` |
| `static\dashboard.js` | `/api/logs/recent?limit=120` |
| `static\dashboard.js` | `/api/meta` |
| `static\dashboard.js` | `/api/orders/recent?limit=50` |
| `static\dashboard.js` | `/api/portfolio/summary` |
| `static\dashboard.js` | `/api/positions/open` |
| `static\dashboard.js` | `/api/signals/recent?limit=50` |
| `static\dashboard.js` | `/api/state` |
| `static\dashboard.js` | `/api/stats/equity?days=1` |
| `static\dashboard.js` | `/api/stats/strategies?days=1` |
| `static\dashboard.js` | `/api/summary/today` |

---

## 4. Data & Artifacts

The code references these key artifacts (JSON/CSV state and logs):

| Artifact | Purpose (inferred) |
| -------- | ------------------ |
| `live_quotes.json` | Live market quotes cache used by the dashboard. |
| `live_state.json` | Live trading state checkpoint. |
| `orders.csv` | Order journal / trade log. |
| `paper_state.json` | Paper trading state checkpoint. |
| `signals.csv` | Strategy signal log. |

## 5. Secrets & Config

Secret files referenced in code (ensure they stay out of git):

| Secret File | Description (keys only) |
| ----------- | ------------------------ |
| `secrets/kite.env` | Holds KITE_API_KEY and KITE_API_SECRET (Zerodha app credential pair). |
| `secrets/kite_tokens.env` | Holds KITE_ACCESS_TOKEN and related tokens from the latest login session. |

## 6. Ops & Run

Typical commands (adapt for your environment):

- `uvicorn scripts.run_dashboard:app --reload` - run the dashboard locally
- `python -m scripts.run_day --login --engines all` - login and start engines
- `python -m scripts.run_day --engines none` - refresh tokens only
- `python -m scripts.replay_from_historical --date YYYY-MM-DD` - replay a historical session

_Generated by `tools/docs/repo_audit.py`._
