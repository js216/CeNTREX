from typing import List


def split(string: str, separator: str = ",") -> List[str]:
    return [x.strip() for x in string.split(separator)]
