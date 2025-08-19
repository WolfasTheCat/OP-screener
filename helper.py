def human_format(num: float) -> str:
    """
    Convert a number into human-readable format with suffix K, M, B, T.
    Always keeps 2 decimal places.
    Examples:
        1234 -> "1.23K"
        250000000 -> "250.00M"
        540000000000 -> "540.00B"
        1200000000000 -> "1.20T"
    """
    num = float(num)
    abs_num = abs(num)

    if abs_num >= 1e12:
        return f"{num/1e12:.2f}T"
    elif abs_num >= 1e9:
        return f"{num/1e9:.2f}B"
    elif abs_num >= 1e6:
        return f"{num/1e6:.2f}M"
    elif abs_num >= 1e3:
        return f"{num/1e3:.2f}K"
    else:
        return f"{num:.2f}"