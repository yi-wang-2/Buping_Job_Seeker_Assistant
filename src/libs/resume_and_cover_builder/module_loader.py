"""
This module is used to store the global configuration of the application.
"""
# app/libs/resume_and_cover_builder/module_loader.py
import importlib
import sys

def load_module(module_path: str, module_name: str):
    # 先从 sys.modules 中删除已存在的模块（如果存在），强制重新加载
    if module_name in sys.modules:
        del sys.modules[module_name]
    
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module