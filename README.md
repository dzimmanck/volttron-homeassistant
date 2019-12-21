# volttron-homeassistant
Volttron agent for homeassistant integration.  It uses the Home Assistant websocket API for low-latency anycronous communication between volttron agents and entities within Home Assistant.

## agent configuration
The agent is configured with three settings.

| name        | description           |
| ------------- |:-------------:|
| ip_address      | The IP address of your Home Assistant server |
| access_token     | The long lived access token for the websocket API (see how to generate one below) |
| topic | The base topic for publishing entity state changes as they occur (see syntax below)     |



## getting an access token
The easiest way to generate a token is from the bottom of your Home Assistant profile page.

![TOKEN](images/generating_tokens.jpg)

## event changes
The agent subscribes to all state changes and publishes change events to the VIP as they occur.  RPCs to do selctive subscription may be added in the future.  Other agents can subscribe to topics published by the HomeAssistantAgent to do asyncronous controls (i.e.  Turn a fan on when a temp gets below a threashol, etc).

The topics are formulated with the following syntax:

<config['topic']>/entity_id/state/<new state of device>
<config['topic']>/entity_id/attributes/<new attributes of device>
  
The '.'s in the entity_id are replaced with '/'s to comply with Volttron's topic syntax.

## control
Home Assistant devices can be controlled through the HomeAssistantAgent by invoking the call_service() remote procedure call.

```python
domain = "switch"
service = "turn_off"
service_data = {"entity_id": "switch.master_bedroom"}
self.vip.rpc.call('homeassistantagent-0.1_1', "call_service", domain, service, service_data)
```
