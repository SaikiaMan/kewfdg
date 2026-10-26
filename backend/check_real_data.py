from app.client.elexon import actual_wind, wind_forecast
from app.services.data_store import DataStore
from app.services.forecast_selector import select_latest_forecast
from app.services.metrics import build_evaluation_frame, summary


def main():
    delivery_date = "2026-01-02"

    print("Fetching actual wind generation...")
    actuals_raw = actual_wind(delivery_date, delivery_date)

    print("Fetching forecast publications...")
    forecasts_raw = wind_forecast(
        "2025-12-25T00:00:00Z",
        "2026-01-01T09:00:00Z",
    )

    # The stream endpoints should return lists of records.
    if not isinstance(actuals_raw, list):
        raise ValueError(
            f"Expected actuals list, received: {type(actuals_raw).__name__}"
        )

    if not isinstance(forecasts_raw, list):
        raise ValueError(
            f"Expected forecasts list, received: {type(forecasts_raw).__name__}"
        )

    print(f"Raw actual records: {len(actuals_raw)}")
    print(f"Raw forecast records: {len(forecasts_raw)}")

    store = DataStore.from_raw(actuals_raw, forecasts_raw)
    print(f"Actual record count: {len(store.actuals)}")

    selected = select_latest_forecast(
        store.forecasts,
        delivery_date,
        cutoff_hhmm="09:00",
    )

    print("\nSelected forecasts:")
    print(selected.head().to_string(index=False))
    print(f"\nSelected native forecast count: {len(selected)}")

    evaluation = build_evaluation_frame(selected, store.actuals)

    print(f"Matched evaluation count: {len(evaluation)}")
    print("\nAccuracy metrics:")
    print(summary(evaluation))

    store.save("data")
    print("\nSaved downloaded data to data/")


if __name__ == "__main__":
    main()