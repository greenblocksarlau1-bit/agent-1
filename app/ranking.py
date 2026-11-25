"""Offer ranking: interest and bookings raise the score; unavailable offers drop."""


def refresh_scores(conn) -> None:
    conn.execute("""
        UPDATE offers SET efficiency_score = (
            SELECT COUNT(*) FROM customer_offers co WHERE co.offer_id = offers.id AND co.relation = 'interested'
        ) + 3 * (
            SELECT COUNT(*) FROM customer_offers co WHERE co.offer_id = offers.id AND co.relation = 'reservation'
        ) - CASE WHEN offers.availability = 'available' THEN 0 ELSE 50 END
    """)
    conn.commit()
