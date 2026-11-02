from .Alert import Alert, State
from .CoolingLost import CoolingLost
from .Critical import Critical
from .FridgeWarming import FridgeWarming
from .HotOilTemp import HotOilTemp
from .HotWaterTemp import HotWaterTemp
from .LosingVacuum import LosingVacuum
from .MagnetQuench import MagnetQuench
from .MxcAbove1K import MxcAbove1K
from .PulseTubeOff import PulseTubeOff
from .UnresponsiveFridge import UnresponsiveFridge

#: Alert types configurable from config.yaml. Watchtower looks alerts up here by name rather
#: than eval()ing the YAML key, which used to make config.yaml arbitrary code execution.
REGISTRY = {
    cls.__name__: cls
    for cls in (
        CoolingLost, Critical, FridgeWarming, HotOilTemp, HotWaterTemp,
        LosingVacuum, MagnetQuench, MxcAbove1K, PulseTubeOff, UnresponsiveFridge,
    )
}

__all__ = ['Alert', 'State', 'REGISTRY'] + list(REGISTRY)
