# utils/filters.py

def format_inr(amount):
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return "₹0.00"

    negative = amount < 0
    amount = abs(amount)

    s = f"{amount:.2f}"
    integer, decimal = s.split(".")

    if len(integer) > 3:
        last3 = integer[-3:]
        rest = integer[:-3]
        rest = ",".join([rest[max(i - 2, 0):i] for i in range(len(rest), 0, -2)][::-1])
        formatted = rest + "," + last3
    else:
        formatted = integer

    result = f"₹{formatted}.{decimal}"
    return f"-{result}" if negative else result
