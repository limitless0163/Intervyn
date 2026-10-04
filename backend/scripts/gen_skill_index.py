"""技能索引维护入口：python -m scripts.gen_skill_index。"""

from app.services.skilllib.gen_index import update_readme


def main() -> None:
    path = update_readme()
    print(f"regenerated pack index in {path}")


if __name__ == "__main__":
    main()
