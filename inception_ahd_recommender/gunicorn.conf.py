import logging
import yaml

with open("docker-compose.yml") as stream:
    try:
        docker_yaml = yaml.safe_load(stream)
        env = {entry.split("=")[0].lower(): entry.split("=")[1]
               for entry in docker_yaml.get("services", {}).get("ahd-deid-recommender", {}).get("environment", [])}
    except yaml.YAMLError as err:
        logging.error(err)
        logging.error("Using default values for workers and address.")
        env = {}

workers = env.get("recommender_workers", 2)
bind = env.get("recommender_address", "127.0.0.1:8000")
log_level = 'info'
wsgi_app = "main:app"