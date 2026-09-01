"""Production Readiness DTOs（自主迭代 04 — 生产就绪度）。

回答「这部作品还差什么才能产出一致画面」：三类确定性缺口在生成前可见——
角色 MASTER 参考图覆盖 / 场景地点绑定覆盖 / 开放连续性警告。全部由真实
Project State 聚合（不假设、不伪造进度），规则驱动、无 LLM。
"""

from pydantic import BaseModel, Field


class ReadinessMetric(BaseModel):
    """通用就绪度：ready = 达标数，missing = 待补缺口（行动点）。"""

    total: int = 0
    ready: int = 0
    missing: int = 0


class SceneBindingReadiness(BaseModel):
    """场景地点绑定覆盖（Scene Consistency 就绪度）。

    bound = 已绑定地点（scene.location_id 非空）；
    bound_with_master = 绑定且该地点有 MASTER 版本（生成可注入地点参考图）；
    unbound = 未绑定地点（绑定入口在分镜板场景头）。
    """

    scenes_total: int = 0
    bound: int = 0
    bound_with_master: int = 0
    unbound: int = 0


class ReadinessRead(BaseModel):
    """GET /projects/{id}/readiness 载荷（契约 §103.1）。"""

    characters: ReadinessMetric = Field(default_factory=ReadinessMetric)  # ready = 有 MASTER 参考图
    scene_binding: SceneBindingReadiness = Field(default_factory=SceneBindingReadiness)
    continuity_open: int = 0
