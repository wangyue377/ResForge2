"""
科研助手插件 — 注册到 Agent

从 research/plugin/plugin.py 导入 ResearchPlugin，
触发 Plugin.__init_subclass__ 自动注册。
"""
from research.plugin.plugin import ResearchPlugin as _

# PluginManager 通过 import_path（__name__）查找已注册的 Plugin 类。
# 类定义在 research.plugin.plugin 中，但 PluginManager 用 akasic_plugin_plugins_research 查找，
# 两者不一致，因此需要显式注册别名。
from agent.plugins.registry import plugin_registry
plugin_registry._classes[__name__] = _
