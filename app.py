from app import create_app

app = create_app()

if __name__ == "__main__":
    from app.utils.logging_config import configure_logging
    import logging

    configure_logging()
    logging.getLogger(__name__).info(
        "Country Guide Reconciliation System starting",
        extra={"stage": "startup", "source_url": None},
    )
    app.run(debug=True, host="0.0.0.0", port=8080)
