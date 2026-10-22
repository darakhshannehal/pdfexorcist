"""Engines that share a lab or a reading: each family votes once."""

from collections.abc import Callable

import pandas as pd


def _family(families: dict[str, list[str]]) -> Callable[[str], str]:
    """Map each engine to its family or itself."""
    family = {m: f for f, ms in families.items() for m in ms}
    return lambda m: family.get(m, m)


def _family_vote(df: pd.DataFrame, key: list[str], families: dict[str, list[str]]) -> pd.DataFrame:
    """Replace each family with its unambiguous vote."""
    df = df.assign(method=df.method.map(_family(families)))
    n = df.groupby([*key, "method", "value"], sort=False).size().rename("n").reset_index()
    top = n[n.n == n.groupby([*key, "method"]).n.transform("max")]
    top = top[top.groupby([*key, "method"]).value.transform("size") == 1]
    first = df.drop_duplicates([*key, "method", "value"])
    return top[[*key, "method", "value"]].merge(first, on=[*key, "method", "value"])


def default_min_agree(voters: int, families: bool = False) -> int:
    """A strict majority of the voters, at least 3 (at least 2 when families vote)."""
    return max(2 if families else 3, voters // 2 + 1)
