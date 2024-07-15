import threading
import paho.mqtt.client as mqtt
import time
import json

# MQTT broker IP address
broker_address = "47.103.78.49"

# Global variables to store received data
sim_downlink_sent_count = 0
act_downlink_sent_count = 0
sim_downlink_received_count = 0
sim_uplink_received_count = 0
act_uplink_received_count = 0
experiment_parameters = []

# Experiment parameters
packet_count = 0
packet_size = 0
repeat_count = 0
repeat_interval = 0
timeout = 0

# State machine for managing current phase
current_phase = 1
current_test = 0
sent_timestamps = 0
sim_uplink_received_start_time = 0
act_uplink_received_start_time = 0
device_receiving_over = False
pc_receiving_over = False

pc_uplink_timer = None
device_uplink_timer = None

pc_ready_for_next_test = False
device_ready_for_next_test = False
pc_timeout_triggered = False
device_timeout_triggered = False


def reset_pc_uplink_timer(client):
    global pc_uplink_timer, timeout, pc_timeout_triggered
    if pc_uplink_timer:
        pc_uplink_timer.cancel()
    pc_uplink_timer = threading.Timer(timeout, handle_pc_uplink_timeout, [client])
    pc_timeout_triggered = False
    pc_uplink_timer.start()


def reset_device_uplink_timer(client):
    global device_uplink_timer, timeout, device_timeout_triggered
    if device_uplink_timer:
        device_uplink_timer.cancel()
    device_uplink_timer = threading.Timer(timeout, handle_device_uplink_timeout, [client])
    device_timeout_triggered = False
    device_uplink_timer.start()


def handle_pc_uplink_timeout(client):
    global pc_receiving_over, device_receiving_over, current_phase, pc_uplink_timer, pc_timeout_triggered
    if pc_timeout_triggered:
        return
    pc_timeout_triggered = True
    pc_uplink_timer = None
    client.publish("/result/step3", f"sim_uplink_received_count,{sim_uplink_received_count}")
    client.publish("/control", "PC uplink receiving over")
    current_phase = 3


def handle_device_uplink_timeout(client):
    global device_receiving_over, pc_receiving_over, current_phase, device_uplink_timer, device_timeout_triggered
    if device_timeout_triggered:
        return
    device_timeout_triggered = True
    device_uplink_timer = None
    client.publish("/result/step3", f"act_uplink_received_count,{act_uplink_received_count}")
    client.publish("/control", "Device uplink receiving over")
    current_phase = 4


def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    # Subscribing to necessary topics
    client.subscribe("/config")
    client.subscribe("/control")
    client.subscribe("/uplink/pc")
    client.subscribe("/uplink/device")
    client.subscribe("/downlink/pc")
    client.subscribe("/downlink/device")


def on_message(client, userdata, msg):
    global sim_downlink_sent_count, act_downlink_sent_count, sim_downlink_received_count, \
        sim_uplink_received_count, sim_uplink_received_start_time, act_uplink_received_count, \
        act_uplink_received_start_time, pc_receiving_over, device_receiving_over, \
        pc_uplink_timer, device_uplink_timer

    global packet_count, packet_size, timeout, repeat_count, repeat_interval

    global current_test, sent_timestamps, current_phase, experiment_parameters

    global pc_ready_for_next_test, device_ready_for_next_test
    i = 1
    try:
        payload = msg.payload.decode()
    except UnicodeDecodeError:
        print(f"Decode error: Skipping message from topic {msg.topic}")
        return
    if msg.topic == "/config":
        print(f"Received message: {payload} on topic {msg.topic}")
        client.subscribe("/control")
        experiment_parameters = json.loads(payload)
        packet_count = experiment_parameters['Packet_count']
        packet_size = experiment_parameters['Packet_size']
        repeat_count = experiment_parameters['Repeat_count']
        repeat_interval = experiment_parameters['Repeat_interval']
        timeout = experiment_parameters['Timeout']
        print("Experiment parameters received:", experiment_parameters)
    if msg.topic == "/control":
        print(f"Received message: {payload} on topic {msg.topic}")
        if "Experiment Start" in payload and current_phase == 1:
            time.sleep(3)
            send_downlink_packets(client)
        elif "PC is about to send uplink messages" in payload and current_phase == 2:
            client.publish("/control", "Ready for PC messages")
        elif "Device is about to send uplink messages" in payload and current_phase == 3:
            client.publish("/control", "Ready for Device messages")
        elif "PC is about to test RTT" in payload and current_phase == 4:
            client.publish("/control", "Ready for PC RTT")
        elif "PC RTT Test Over" in payload and current_phase == 4:
            current_phase = 5
        elif "Device is about to test RTT" in payload and current_phase == 5:
            client.publish("/control", "Ready for Device RTT")
        elif "PC Ready for Next Test" in payload:
            pc_ready_for_next_test = True
            if device_ready_for_next_test:
                next_test(client)
        elif "Device Ready for Next Test" in payload:
            device_ready_for_next_test = True
            if pc_ready_for_next_test:
                next_test(client)
    if msg.topic == "/uplink/pc" and current_phase == 2:
        print("PC uplink message received")
        sim_uplink_received_count += 1
        if sim_uplink_received_count == 1:
            sim_uplink_received_start_time = time.time()
        elif sim_uplink_received_count == packet_count:
            handle_pc_uplink_timeout(client)
        else:
            reset_pc_uplink_timer(client)

    if msg.topic == "/uplink/pc" and current_phase == 4:
        client.publish("/downlink/pc", payload)

    if msg.topic == "/uplink/device" and current_phase == 5:
        client.publish("/downlink/device", payload)
        print(i)
        i += 1

    if msg.topic == "/uplink/device" and current_phase == 3:
        print("Device uplink message received")
        act_uplink_received_count += 1
        if act_uplink_received_count == 1:
            act_uplink_received_start_time = time.time()
        elif act_uplink_received_count == packet_count:
            handle_device_uplink_timeout(client)
        else:
            reset_device_uplink_timer(client)


def send_downlink_packets(client):
    global sim_downlink_sent_count, act_downlink_sent_count, packet_count, packet_size, current_phase
    sim_downlink_sent_count = 0
    act_downlink_sent_count = 0
    for i in range(packet_count):
        feedback_pc = client.publish("/downlink/pc", "c" * packet_size)
        if feedback_pc.rc == 0:
            sim_downlink_sent_count += 1
        feedback_device = client.publish("/downlink/device", "e" * packet_size)
        if feedback_device.rc == 0:
            act_downlink_sent_count += 1
    client.publish("/result/step2", f"sim_downlink_sent_count,{sim_downlink_sent_count}")
    client.publish("/result/step2", f"act_downlink_sent_count,{act_downlink_sent_count}")
    current_phase = 2


def next_test(client):
    global current_test, repeat_count, repeat_interval, current_phase
    global sim_downlink_sent_count, sim_uplink_received_count, act_downlink_sent_count, act_uplink_received_count
    global pc_receiving_over, device_receiving_over
    global pc_uplink_timer, device_uplink_timer
    global pc_ready_for_next_test, device_ready_for_next_test
    current_test += 1
    if current_test < repeat_count:
        print(f"Cloud Starting test {current_test + 1}")
        current_phase = 1
        sim_downlink_sent_count = 0
        act_downlink_sent_count = 0
        sim_uplink_received_count = 0
        act_uplink_received_count = 0
        pc_receiving_over = False
        device_receiving_over = False
        pc_ready_for_next_test = False
        device_ready_for_next_test = False
        send_downlink_packets(client)
        time.sleep(repeat_interval)
        # if pc_uplink_timer:
        #    pc_uplink_timer.cancel()
        # if device_uplink_timer:
        #    device_uplink_timer.cancel()
    else:
        print("Experiment completed. Waiting for next experiment.")
        current_phase = 1
        current_test = 0
        sim_downlink_sent_count = 0
        act_downlink_sent_count = 0
        sim_uplink_received_count = 0
        act_uplink_received_count = 0
        pc_receiving_over = False
        device_receiving_over = False
        client.unsubscribe("/control")


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(broker_address, 1883, 60)

    client.loop_start()

    print("Cloud server is running and waiting for experiments.")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
