"""WSGI entry point for the Zebra label app."""

import logging
import os

from zebra import create_app

logging.basicConfig(
    filename='zebra_app.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
)

app = create_app()

if __name__ == '__main__':
    logging.info('Starting Zebra Label Flask App')
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'
    app.run(debug=debug)
