"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.messaging.health import (STATUS_BAD,
                                                STATUS_UNKNOWN,
                                                STATUS_GOOD,
                                                STATUS_STARTING,
                                                Status)


from gevent import monkey
monkey.patch_all()

import websocket
import json
import time

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def homeassistant(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Homeassistant
    :rtype: Homeassistant
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    ip_address = str(config['ip_address'])
    access_token = str(config['access_token'])
    topic = str(config.get('topic', 'datalogger/homeassistant'))

    return Homeassistant(ip_address, access_token, topic, **kwargs)


class Homeassistant(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, ip_address, access_token, topic = 'datalogger/homeassistant', **kwargs):
        super(Homeassistant, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.ip_address = ip_address
        self.access_token = access_token
        self.topic = topic

        self.default_config = {"ip_address": ip_address,
                               "access_token": access_token,
                               "topic": topic}

        # websocket attributes
        self.ws = None
        self.ws_thread = None

        # message for websocket interactions
        self.msg_id = 2

        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """

        # close the previous web socket if there was one
        if self.ws is not None:
            self.ws.close()
        
        # also kill the thread if there was one
        if self.ws_thread is not None:
            self.ws_thread.kill()

        config = self.default_config.copy()
        config.update(contents)

        _log.debug("Configuring Agent")

        try:
            ip_address = str(config["ip_address"])
            access_token = str(config["access_token"])
            topic = str(config["topic"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.ip_address = ip_address
        self.access_token = access_token
        self.topic = topic

        # create the web socket app
        def on_open(ws):
            # authenticate
            ws.send(json.dumps({'type': 'auth', 'access_token': access_token}))

            # subscribe
            ws.send(json.dumps({'id': 1, 'type': 'subscribe_events', 'event_type': 'state_changed'}))

        def on_error(ws, error):
            self.vip.health.set_status(STATUS_BAD,error)

        def on_message(ws, message):
            data = json.loads(message)

            # auto-increment the message id
            try:
                msg_id = data['id']
                if msg_id >= self.msg_id:
                    self.msg_id = msg_id + 1
            except KeyError:
                pass

            # If an event is detected, parse into a topic/message structure and publish to the vip
            if data["type"] == "event":
                event = data["event"]
                entity_id = event["data"]["entity_id"]
                entity_subtopic = entity_id.replace('.', '/')
                state = event["data"]["new_state"]["state"]
                attributes = event["data"]["new_state"]["attributes"]
                ts = event["data"]["new_state"]["last_updated"]  # FIXME:  Does this need re-formatting for Volttron?
                headers = {
                    headers_mod.DATE: ts,
                    headers_mod.TIMESTAMP: ts
                }

                # simple log of state changes
                _log.debug(f'{entity_id} --> {state}')

                # publish state
                topic = '/'.join([self.topic, entity_subtopic, 'state'])
                self.vip.pubsub.publish('pubsub',
                                    topic,
                                    headers=headers,
                                    message=state).get(timeout=10)

                # publish state attributes
                topic = '/'.join([self.topic, entity_subtopic, 'attributes'])
                self.vip.pubsub.publish('pubsub',
                                    topic,
                                    headers=headers,
                                    message=attributes).get(timeout=10)


        self.vip.health.set_status(STATUS_STARTING,"Starting web socket")

        _log.debug('Creating web socket')
        self.ws = websocket.WebSocketApp(f'ws://{ip_address}:8123/api/websocket',
                                         on_message = on_message,
                                         on_open = on_open)

        # spawn a thread for running the web socket
        _log.debug('Starting web socket')
        self.ws_thread = self.core.spawn(self.ws.run_forever)
        _log.debug('Web socket running')
        self.vip.health.set_status(STATUS_GOOD, "Successfull started web socket")

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        _log.debug('Closing web-socket')
        self.ws.close()
        _log.debug('Killing web-socket thread')
        self.ws_thread.kill()

    @RPC.export
    def call_service(self, domain, service, service_data=None):
        """
        Remote procedure call for sending commands to HomeAssistant devices using the websocket API

        See https://developers.home-assistant.io/docs/en/external_api_websocket.html
        """

        _log.debug("Received service call.")
        msg = {"id": self.msg_id, "type": "call_service","domain": domain,"service": service}
        if service_data:
            msg["service_data"] = service_data
        
        # send message
        self.ws.send(json.dumps(msg))

def main():
    """Main method called to start the agent."""
    utils.vip_main(homeassistant, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
