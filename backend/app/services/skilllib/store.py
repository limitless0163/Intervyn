"""读写带 YAML 元数据的技能文件；检索扫描正式库后仅返回匹配且排名靠前的技能。

YAML 自动解析的日期需转为 ISO 字符串，才能通过字符串字段校验。
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import yaml

from .models import Skill, SkillFrontmatter

# 根据模块位置定位 backend 根目录，避免依赖工作目录。
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SKILLS_DIR = _BACKEND_ROOT / "skills"

_FENCE = "---"


def default_skills_dir() -> Path:
    """返回仓库中的 backend/skills 正式技能目录。"""
    return DEFAULT_SKILLS_DIR


def slugify(*, company: str, role: str, level: str) -> str:
    """统一公司、岗位和级别的标识，用于技能 ID、文件名及合并键。

    转为小写，连续非字母数字字符折叠为一个连字符。
    """
    raw = f"{company}-{role}-{level}".lower()
    cleaned: list[str] = []
    prev_dash = False
    for ch in raw:
        if ch.isalnum():
            cleaned.append(ch)
            prev_dash = False
        elif not prev_dash:
            cleaned.append("-")
            prev_dash = True
    return "".join(cleaned).strip("-")


def _coerce_scalars(data: dict) -> dict:
    """将 YAML 自动解析的日期或时间转换为 ISO 字符串。"""
    out: dict = {}
    for key, value in data.items():
        if isinstance(value, (_dt.date, _dt.datetime)):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


def parse_skill(text: str) -> Skill:
    """解析 YAML 元数据分隔块及 Markdown 正文，无效格式抛出 ValueError。"""
    if not text.lstrip().startswith(_FENCE):
        raise ValueError("skill file must start with a '---' frontmatter fence")
    # 只按前两个元数据分隔符切分，后续正文中的分隔符保留。
    stripped = text.lstrip("\n")
    parts = stripped.split(_FENCE, 2)
    if len(parts) < 3:
        raise ValueError("skill file is missing the closing '---' frontmatter fence")
    _, raw_front, body = parts
    data = yaml.safe_load(raw_front) or {}
    if not isinstance(data, dict):
        raise ValueError("skill frontmatter must be a YAML mapping")  # noqa: TRY004 - 调用方统一捕获技能文件的 ValueError
    frontmatter = SkillFrontmatter.model_validate(_coerce_scalars(data))
    return Skill(frontmatter=frontmatter, body_md=body.lstrip("\n"))


def serialize_skill(skill: Skill) -> str:
    """将技能序列化为 YAML 元数据分隔块及 Markdown 正文。"""
    front = yaml.safe_dump(
        skill.frontmatter.model_dump(),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    body = skill.body_md.rstrip("\n")
    return f"{_FENCE}\n{front}{_FENCE}\n\n{body}\n"


def load_skill(path: str | Path) -> Skill:
    """读取并解析单个技能文件。"""
    return parse_skill(Path(path).read_text(encoding="utf-8"))


def save_skill(skill: Skill, path: str | Path) -> Path:
    """序列化技能并写入指定路径，按需创建父目录。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(serialize_skill(skill), encoding="utf-8")
    return p


def _is_skill_file(path: Path) -> bool:
    """仅识别以 YAML 元数据分隔符开头的 Markdown 文件。"""
    if path.suffix != ".md":
        return False
    try:
        with path.open("r", encoding="utf-8") as fh:
            head = fh.read(8)
    except OSError:
        return False
    return head.lstrip().startswith(_FENCE)


def list_skills(skills_dir: str | Path | None = None) -> list[Skill]:
    """只扫描正式库顶层，跳过说明文件和待审子目录；解析失败的技能不返回。"""
    root = Path(skills_dir) if skills_dir is not None else DEFAULT_SKILLS_DIR
    if not root.exists():
        return []
    skills: list[Skill] = []
    for path in sorted(root.glob("*.md")):
        if not _is_skill_file(path):
            continue
        try:
            skills.append(load_skill(path))
        except (ValueError, yaml.YAMLError):
            continue
    return skills


#: generic 技能作为任意公司的回退参考。
GENERIC_COMPANY = "generic"

#: 排名依次优先 promoted、in-review、draft。
_STATUS_RANK = {"promoted": 0, "review": 1, "draft": 2}

#: 置信度按距 last_verified 的天数衰减，单位为半衰期天数。
_CONFIDENCE_HALF_LIFE_DAYS = 180.0


# 查询与技能角色都扩展复合词，兼容 Front End 与 frontend 等等价写法。
_COMPOUND_FORMS: dict[str, tuple[str, ...]] = {
    "frontend": ("front", "end"),
    "backend": ("back", "end"),
    "fullstack": ("full", "stack"),
    "devops": ("dev", "ops"),
    "qa": ("quality", "assurance"),
    "ml": ("machine", "learning"),
    "ai": ("artificial", "intelligence"),
    "sre": ("site", "reliability", "engineer"),
    "tpm": ("technical", "program", "manager"),
}

# 扩展岗位同义词，避免 Developer、Engineering 等常见名称错过 Engineer 技能。
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"engineer", "engineering", "developer", "dev"}),
)


def _expand_role_tokens(tokens: set[str]) -> set[str]:
    """扩展角色词的等价写法，使职位名称与技能标识可比较。"""
    expanded = set(tokens)
    for joined, parts in _COMPOUND_FORMS.items():
        if joined in tokens:
            expanded.update(parts)
        elif all(part in tokens for part in parts):
            expanded.add(joined)
    for group in _SYNONYM_GROUPS:
        if expanded & group:
            expanded |= group
    return expanded


def _role_tokens(text: str) -> set[str]:
    """提取小写字母数字角色词，并扩展 Front End、ML、Developer 等等价写法。"""
    tokens: set[str] = set()
    current: list[str] = []
    for ch in text.lower():
        if ch.isalnum():
            current.append(ch)
        elif current:
            tokens.add("".join(current))
            current = []
    if current:
        tokens.add("".join(current))
    return _expand_role_tokens(tokens)


def effective_confidence(
    fm: SkillFrontmatter, *, today: _dt.date | None = None
) -> float:
    """按验证日期衰减置信度，默认半衰期为 180 天；无效日期不衰减，未来日期按零龄处理。"""
    try:
        verified = _dt.date.fromisoformat(fm.last_verified[:10])
    except ValueError:
        return fm.confidence
    now = today or _dt.datetime.now(tz=_dt.UTC).date()
    age_days = max(0, (now - verified).days)
    return fm.confidence * 0.5 ** (age_days / _CONFIDENCE_HALF_LIFE_DAYS)


def find_relevant(
    skills_dir: str | Path | None = None,
    *,
    company: str,
    role: str,
    level: str | None = None,
    limit: int = 2,
) -> list[Skill]:
    """返回前 limit 个匹配技能，排除 deprecated 状态。

    技能角色词须为查询角色词的子集；仅匹配指定公司或 generic。
    依次按公司、级别、状态、时间衰减后的置信度和技能 ID 排序；级别为软匹配。
    """
    want_company = company.strip().lower()
    want_role = _role_tokens(role)
    want_level = level.strip().lower() if level else None

    scored: list[tuple[int, int, int, float, str, Skill]] = []
    for skill in list_skills(skills_dir):
        fm = skill.frontmatter
        if fm.status == "deprecated":
            continue
        pack_company = fm.company.strip().lower()
        if pack_company == want_company:
            company_tier = 0
        elif pack_company == GENERIC_COMPANY:
            company_tier = 1
        else:
            continue
        pack_role = _role_tokens(fm.role)
        if not pack_role or not pack_role <= want_role:
            continue
        level_tier = 0 if want_level is None or fm.level.strip().lower() == want_level else 1
        status_tier = _STATUS_RANK.get(fm.status, 3)
        scored.append(
            (company_tier, level_tier, status_tier, -effective_confidence(fm), fm.id, skill)
        )
    scored.sort(key=lambda item: item[:5])
    return [item[5] for item in scored[:limit]]
