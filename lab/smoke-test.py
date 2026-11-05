"""Exercise the local storefront with an isolated session and mock payment."""

from datetime import date
from http.cookiejar import CookieJar
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, ProxyHandler, build_opener


BASE_URL = "http://127.0.0.1:18080"
PRODUCT_ID = "OLJCESPC7Z"


def main():
    client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
    steps = [
        ("Browse catalog", "/", b"Sunglasses", None),
        ("Open product", f"/product/{PRODUCT_ID}", b"Add To Cart", None),
        (
            "Add product to cart",
            "/cart",
            b"cart-checkout-form",
            {"product_id": PRODUCT_ID, "quantity": "1"},
        ),
        (
            "Place mock order",
            "/cart/checkout",
            b"Your order is complete!",
            {
                "email": "lab@example.com",
                "street_address": "123 Example Street",
                "zip_code": "94043",
                "city": "Mountain View",
                "state": "CA",
                "country": "United States",
                "credit_card_number": "4111111111111111",
                "credit_card_expiration_month": "12",
                "credit_card_expiration_year": str(date.today().year + 1),
                "credit_card_cvv": "123",
            },
        ),
    ]

    for label, path, expected, form in steps:
        data = urlencode(form).encode() if form is not None else None
        try:
            with client.open(BASE_URL + path, data, timeout=20) as response:
                if response.status != 200 or expected not in response.read():
                    raise SystemExit(f"{label}: expected storefront response at {path}")
                print(f"{label}: HTTP {response.status}")
        except (URLError, TimeoutError) as error:
            raise SystemExit(f"{label}: {error}") from error


if __name__ == "__main__":
    main()
