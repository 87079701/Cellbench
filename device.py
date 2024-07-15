import paho.mqtt.client as mqtt
import time
import json

# MQTT broker IP address
broker_address = "47.103.78.49"

# Global variables to store received data
act_downlink_received_count = 0
act_downlink_received_time = 0
act_uplink_sent_count = 0
act_uplink_sent_time = 0
act_uplink_received_count = 0
acknowledged = False
sent_timestamps = {}
act_downlink_sent_count = 0

# Experiment parameters
packet_count = 100  # Example value, replace with actual
packet_size = 256  # Example value, replace with actual
repeat_count = 3  # Example value, replace with actual
repeat_interval = 5  # Example value, replace with actual
timeout = 5  # Example value, replace with actual
retrans_count = 3  # Example value, replace with actual
module = "TestModule"  # Example value, replace with actual
operator = "TestOperator"  # Example value, replace with actual

experiment_parameters = {
    "Packet_count": packet_count,
    "Packet_size": packet_size,
    "Repeat_count": repeat_count,
    "Repeat_interval": repeat_interval,
    "Timeout": timeout,
    "Retrans_count": retrans_count,
    "Module": module,
    "Operator": operator
}

# State machine for managing current phase
current_phase = 1
current_test = 0
start_time = 0

# Callback for when the client receives a CONNACK response from the server
def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    # Subscribing to necessary topics
    # client.subscribe("/config")
    client.subscribe("/control")
    client.subscribe("/uplink/device")
    client.subscribe("/downlink/device")
    # client.subscribe("/result/step2")
    # client.subscribe("/result/step3")
    # client.subscribe("/result/step4")
    # client.subscribe("/result/step5")
    # client.subscribe("/result")

    # Publish the experiment parameters to /config
    client.publish("/config", json.dumps(experiment_parameters))
    print("Experiment parameters sent to /config")
    time.sleep(1)
    client.publish("/control", "Experiment Start")
    client.publish("/control", "Device Ready for Step 2")


# Callback for when a PUBLISH message is received from the server
def on_message(client, userdata, msg):
    global act_downlink_received_count, act_downlink_received_time, start_time
    global act_uplink_sent_count, act_uplink_sent_time
    global act_uplink_received_count
    global current_test
    global experiment_parameters, act_downlink_sent_count, current_phase
    global packet_count, packet_size, timeout, repeat_count, repeat_interval
    payload = msg.payload.decode()
    if msg.topic == "/control":
        print(f"Received message: {payload} on topic {msg.topic}")
        if "PC Ready for Step 2" in payload or current_phase == 1:
            current_phase = 2
        elif "PC Ready for Step 3" in payload and current_phase == 2:
            current_phase = 3
            send_uplink_packets(client)
        elif "PC Ready for Step 6" in payload and current_phase == 3:
            next_test(client)

    if msg.topic == "/downlink/device" and current_phase == 2:
        act_downlink_received_count += 1
        if act_downlink_received_count == 1:
            start_time = int(time.time() * 1000)
        if act_downlink_received_count == packet_count:
            act_downlink_received_time = int(time.time() * 1000) - start_time
            client.publish("/result/step2", f"act_downlink_received_count,{act_downlink_received_count}")
            client.publish("/result/step2", f"act_downlink_received_time,{act_downlink_received_time}")
            client.publish("/control", "Device Ready for Step 3")


def send_uplink_packets(client):
    global act_uplink_sent_count, act_uplink_sent_time, packet_count, packet_size
    act_uplink_sent_count = 0
    act_uplink_sent_time = float(time.time() * 1000)
    for i in range(packet_count):
        client.publish("/uplink/device", "d" * packet_size)
        act_uplink_sent_count += 1
    act_uplink_sent_time = float(time.time() * 1000) - act_uplink_sent_time
    client.publish("/result/step3", f"act_uplink_sent_count,{act_uplink_sent_count}")
    client.publish("/result/step3", f"act_uplink_sent_time,{act_uplink_sent_time}")



def next_test(client):
    global current_test, repeat_count, repeat_interval, current_phase
    global act_downlink_received_count, act_uplink_sent_count
    current_test += 1
    if current_test < repeat_count:
        print(f"Device Starting test {current_test + 1}")
        time.sleep(repeat_interval)
        act_downlink_received_count = 0
        act_uplink_sent_count = 0
        current_phase = 2
        client.publish("/control", "Device Ready for Step 2")
    else:
        print("Experiment completed.")
        current_phase = 0


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(broker_address, 1883, 60)

    client.loop_start()

    print("Device is ready for the experiment.")
    while True:
        time.sleep(1)

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
