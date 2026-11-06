"""以无界面方式启动本机 ComfyUI（带兼容补丁）。

兼容两件事：
  1. comfy_aimdo 比 main.py 旧 —— 丢掉它不认识的 nvml_pressure 参数
  2. numpy 2.x 删掉了 memmap.newbyteorder —— 补回等价实现

不会修改 ComfyUI 原安装。
"""
import os
import runpy
import sys

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, STUDIO)
sys.path.append(os.path.join(STUDIO, ".pylibs"))  # 项目内依赖（gguf 等）

import paths  # noqa: E402

COMFY_ROOT = paths.COMFY_ROOT
if not COMFY_ROOT or not os.path.isfile(os.path.join(COMFY_ROOT, "main.py")):
    sys.exit("找不到 ComfyUI：请在 studio/config.json 里设置 comfy_root，"
             "或设置环境变量 COMFY_ROOT 指向含 main.py 的目录。")

import comfy_aimdo  # noqa: E402
from comfy_aimdo import control  # noqa: E402

_orig_init = control.init


def _compat_init(*args, **kwargs):
    kwargs.pop("nvml_pressure", None)
    return _orig_init(*args, **kwargs)


control.init = _compat_init
comfy_aimdo.control.init = _compat_init

import numpy as _np  # noqa: E402

if not hasattr(_np.memmap, "newbyteorder"):
    def _memmap_newbyteorder(self, new_order="S"):
        return self.view(self.dtype.newbyteorder(new_order))

    _np.memmap.newbyteorder = _memmap_newbyteorder

paths.ensure_dirs()
os.makedirs(os.path.join(STUDIO, "custom_nodes"), exist_ok=True)
yaml_path = paths.extra_model_paths_yaml(os.path.join(STUDIO, "extra_model_paths.yaml"))

sys.argv = [
    "main.py",
    "--port", "8188",
    "--listen", "127.0.0.1",
    "--preview-method", "none",
    "--output-directory", paths.OUTPUT,
    "--input-directory", paths.INPUT,
    "--temp-directory", paths.TEMP,
    "--extra-model-paths-config", yaml_path,
]
sys.path.insert(0, COMFY_ROOT)
runpy.run_path(os.path.join(COMFY_ROOT, "main.py"), run_name="__main__")
