Format of the BlueFors Logs


- Log directory stored in C:\FridgeLogs
- Folder for each day. Same format inside the fridge

- **CH1 P {{DATE}}.log** -> P1 = Vacuum can
- **CH1 T {{DATE}}.log** -> T1 = Pulse tube 1
- **CH2 P {{DATE}}.log** -> P2 = ...
- **CH2 T {{DATE}}.log** -> T2 = Pulse tube 2
- **CH3 P {{DATE}}.log** -> P3 = ...
- **CH3 T {{DATE}}.log** -> T3 = Magnet
- **CH4 P {{DATE}}.log** -> P4 = Traps
- **CH4 T {{DATE}}.log** -> T4 = ? (missing)
- **CH5 P {{DATE}}.log** -> P5 = Mixture tank
- **CH5 T {{DATE}}.log** -> T5 = Still
- **CH6 P {{DATE}}.log** -> P6 = Air input
- **CH6 T {{DATE}}.log** -> T6 = Mixing chamber

For pressures it is probably best to use `maxigauge {{DATE}}.log`