import json
import time
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import threading

# MQTT broker IP address
broker_address = "47.103.78.49"

# Global variables to store received data
sim_downlink_received_count = 0
sim_downlink_received_time = 0
sim_downlink_latest_received_time = 0
sim_uplink_sent_count = 0
sim_uplink_sent_time = 0
sim_uplink_received_count = 0
sim_downlink_sent_count = 0

act_downlink_received_count = 0
act_downlink_received_time = 0
act_uplink_received_count = 0
act_uplink_sent_count = 0
act_uplink_sent_time = 0
act_downlink_sent_count = 0

sim_rtt = 0
sim_rtt_values = []
sim_rtt_received_count = 0

act_downlink_sent_count_received = False
act_downlink_received_count_received = False
act_downlink_received_time_received = False

act_uplink_sent_count_received = False
act_uplink_sent_time_received = False
act_uplink_received_count_received = False

act_downlink_calculated = False
sim_downlink_calculated = False

sim_uplink_calculated = False
act_uplink_calculated = False

downlink_timer = None
timeout_triggered = False

rtt_timeout_timer = None
current_rtt_id = 0
# Experiment parameters
packet_count = 0
packet_size = 0
repeat_count = 0
repeat_interval = 0
timeout = 0
current_test = 0
experiment_parameters = {}

# State machine for managing current phase
current_phase = 1
sim_downlink_start_time = 0

# Results dictionary to store all results
results = {
    "sim_downlink_received_rate": [],
    "sim_downlink_throughput": [],
    "act_downlink_received_rate": [],
    "act_downlink_throughput": [],
    "sim_uplink_sent_rate": [],
    "sim_uplink_received_rate": [],
    "sim_uplink_throughput": [],
    "act_uplink_sent_rate": [],
    "act_uplink_received_rate": [],
    "act_uplink_throughput": [],
    "sim_average_rtt": [],
    "act_average_rtt": []
}


def reset_downlink_timer():
    global downlink_timer, timeout, timeout_triggered
    if downlink_timer is not None:
        downlink_timer.cancel()
    downlink_timer = threading.Timer(timeout, handle_downlink_timeout)
    timeout_triggered = False
    downlink_timer.start()


def handle_downlink_timeout():
    global sim_downlink_received_time, sim_downlink_start_time, downlink_timer, sim_downlink_latest_received_time, \
        timeout_triggered
    if timeout_triggered:
        return
    timeout_triggered = True
    sim_downlink_received_time = sim_downlink_latest_received_time - sim_downlink_start_time
    # client.publish("/result/step2", f"sim_downlink_received_count,{sim_downlink_received_count}")
    # client.publish("/result/step2", f"sim_downlink_received_time,{sim_downlink_received_time}")


def on_connect(client, userdata, flags, rc):
    client.subscribe("/config")
    client.subscribe("/control")
    client.subscribe("/uplink/pc")
    client.subscribe("/downlink/pc")
    client.subscribe("/result/step2")
    client.subscribe("/result/step3")
    client.subscribe("/result/step4")
    client.subscribe("/result/step5")
    client.subscribe("/result")


def on_message(client, userdata, msg):
    global sim_downlink_start_time
    global sim_downlink_received_count, sim_downlink_received_time, sim_downlink_sent_count, sim_downlink_latest_received_time

    global act_downlink_received_count, act_downlink_sent_count, act_downlink_received_time
    global act_downlink_received_count_received, act_downlink_received_time_received, act_downlink_sent_count_received
    global act_downlink_calculated, sim_downlink_calculated

    global sim_uplink_sent_count, sim_uplink_sent_time, sim_uplink_received_count
    global act_uplink_sent_count, act_uplink_sent_time, act_uplink_received_count
    global act_uplink_sent_count_received, act_uplink_sent_time_received, act_uplink_received_count_received
    global act_uplink_calculated, sim_uplink_calculated

    global sim_rtt,  sim_rtt_received_count

    global current_test, current_phase, current_rtt_id

    global experiment_parameters
    global packet_count, packet_size, timeout, repeat_count, repeat_interval
    global downlink_timer, rtt_timeout_timer
    try:
        payload = msg.payload.decode()
    except UnicodeDecodeError:
        print(f"Decode error: Skipping message from topic {msg.topic}")
        return
    if msg.topic == "/config":
        experiment_parameters = json.loads(payload)
        packet_count = experiment_parameters['Packet_count']
        packet_size = experiment_parameters['Packet_size']
        repeat_count = experiment_parameters['Repeat_count']
        repeat_interval = experiment_parameters['Repeat_interval']
        timeout = experiment_parameters['Timeout']
        print("Experiment parameters received:", experiment_parameters)
    elif msg.topic == "/control":
        print(f"Received message: {payload} on topic {msg.topic}")
        if "Experiment Start" in payload:
            current_phase = 1
        elif "Ready for PC messages" in payload and current_phase == 2:
            send_uplink_packets(client)
        elif "Ready for PC RTT" and current_phase == 3:
            send_rtt_packets(client)

    if msg.topic == "/downlink/pc" and current_phase == 1:
        sim_downlink_received_count += 1
        sim_downlink_latest_received_time = time.time()
        if sim_downlink_received_count == 1:
            sim_downlink_start_time = time.time()
        elif sim_downlink_received_count == packet_count:
            handle_downlink_timeout()
        else:
            reset_downlink_timer()

    if msg.topic == "/downlink/pc" and current_phase == 3:
        parts = payload.split(",")
        timestamp = int(parts[0])
        rtt_id = int(parts[1])
        if rtt_id == current_rtt_id:
            sim_rtt = int(time.time() * 1000) - timestamp
            sim_rtt_values.append(sim_rtt)
            sim_rtt_received_count += 1
            if sim_rtt_received_count < packet_count:
                send_rtt_packets(client)
            else:
                if rtt_timeout_timer is not None:
                    rtt_timeout_timer.cancel()
                average_rtt = sum(sim_rtt_values) / len(sim_rtt_values)
                client.publish("/result", f"sim RTT values: {sim_rtt_values}")
                client.publish("/result", f"Average sim RTT: {average_rtt}")
                results["sim_average_rtt"].append(average_rtt)
                client.publish("/control", "PC RTT Test Over")
                current_phase = 4
            # if rtt_timeout_timer is not None:
            #    rtt_timeout_timer.cancel()

    if msg.topic == "/result/step2" and current_phase == 1:
        print(f"Received message: {payload} on topic {msg.topic}")
        parts = payload.split(',')
        if parts[0] == "sim_downlink_sent_count":
            sim_downlink_sent_count = int(parts[1])
            calculate_sim_downlink_metrics(client)
        elif parts[0] == "act_downlink_sent_count":
            act_downlink_sent_count = int(parts[1])
            act_downlink_sent_count_received = True
            if act_downlink_received_time_received and act_downlink_received_count_received:
                calculate_act_downlink_metrics(client)

        elif parts[0] == "act_downlink_received_count":
            act_downlink_received_count = int(parts[1])
            act_downlink_received_count_received = True
            if act_downlink_received_time_received and act_downlink_sent_count_received:
                calculate_act_downlink_metrics(client)

        elif parts[0] == "act_downlink_received_time":
            act_downlink_received_time = float(parts[1])
            act_downlink_received_time_received = True
            if act_downlink_sent_count_received and act_downlink_received_count_received:
                calculate_act_downlink_metrics(client)

    if msg.topic == "/result/step3" and current_phase == 2:
        print(f"Received message: {payload} on topic {msg.topic}")
        parts = payload.split(',')
        if parts[0] == "sim_uplink_received_count":
            sim_uplink_received_count = int(parts[1])
            calculate_sim_uplink_metrics(client)
        elif parts[0] == "act_uplink_sent_count":
            act_uplink_sent_count = int(parts[1])
            act_uplink_sent_count_received = True
            if act_uplink_received_count_received and act_uplink_sent_time_received:
                calculate_act_uplink_metrics(client)

        elif parts[0] == "act_uplink_received_count":
            act_uplink_received_count = int(parts[1])
            act_uplink_received_count_received = True
            if act_uplink_sent_time_received and act_uplink_sent_count_received:
                calculate_act_uplink_metrics(client)

        elif parts[0] == "act_uplink_sent_time":
            act_uplink_sent_time = float(parts[1])
            act_uplink_sent_time_received = True
            if act_uplink_sent_count_received and act_uplink_received_count_received:
                calculate_act_uplink_metrics(client)

    if msg.topic == "/result":
        parts = payload.split(':')
        print(f"Received message: {payload} on topic {msg.topic}")
        if parts[0] == "Average act RTT":
            act_average_rtt = float(parts[1])
            results["act_average_rtt"].append(act_average_rtt)
            client.publish("/control", "PC Ready for Next Test")
            next_test()


def send_uplink_packets(client):
    global sim_uplink_sent_count, sim_uplink_sent_time, packet_count, packet_size
    sim_uplink_sent_count = 0
    start_time = time.perf_counter()
    for i in range(packet_count):
        feedback = client.publish("/uplink/pc", "p" * packet_size)
        #if feedback.rc == 0:
        sim_uplink_sent_count += 1
    end_time = time.perf_counter()
    sim_uplink_sent_time = (end_time - start_time) * 1000
    # client.publish("/result/step3", f"sim_uplink_sent_count,{sim_uplink_sent_count}")
    # client.publish("/result/step3", f"sim_uplink_sent_time,{sim_uplink_sent_time}")


def calculate_act_downlink_metrics(client):
    global act_downlink_received_count, act_downlink_received_time, act_downlink_sent_count, packet_size
    global act_downlink_calculated, sim_downlink_calculated, current_test, current_phase
    act_downlink_received_rate = act_downlink_received_count / act_downlink_sent_count
    if act_downlink_received_time > 0:
        act_downlink_throughput = act_downlink_received_count * packet_size / act_downlink_received_time
    else:
        act_downlink_throughput = 0
    client.publish("/result", f"current_test,{current_test},act_downlink_received_rate,{act_downlink_received_rate}")
    client.publish("/result", f"current_test,{current_test},act_downlink_throughput,{act_downlink_throughput}")
    results["act_downlink_received_rate"].append(act_downlink_received_rate)
    results["act_downlink_throughput"].append(act_downlink_throughput)
    act_downlink_calculated = True
    if sim_downlink_calculated:
        client.publish("/control", "PC is about to send uplink messages")
        current_phase = 2
        sim_downlink_calculated = False
        act_downlink_calculated = False


def calculate_sim_downlink_metrics(client):
    global sim_downlink_received_count, sim_downlink_received_time, sim_downlink_sent_count, packet_size
    global act_downlink_calculated, sim_downlink_calculated, current_test, current_phase
    sim_downlink_received_rate = sim_downlink_received_count / sim_downlink_sent_count
    if sim_downlink_received_time > 0:
        sim_downlink_throughput = sim_downlink_received_count * packet_size / sim_downlink_received_time
    else:
        sim_downlink_throughput = 0
    client.publish("/result", f"current_test,{current_test},sim_downlink_received_rate,{sim_downlink_received_rate}")
    client.publish("/result", f"current_test,{current_test},sim_downlink_throughput,{sim_downlink_throughput}")
    results["sim_downlink_received_rate"].append(sim_downlink_received_rate)
    results["sim_downlink_throughput"].append(sim_downlink_throughput)
    sim_downlink_calculated = True
    if act_downlink_calculated:
        client.publish("/control", "PC is about to send uplink messages")
        current_phase = 2
        sim_downlink_calculated = False
        act_downlink_calculated = False


def calculate_sim_uplink_metrics(client):
    global sim_uplink_sent_count, sim_uplink_sent_time, sim_uplink_received_count, packet_count, packet_size
    global sim_uplink_calculated, act_uplink_calculated
    global current_phase, current_test
    sim_uplink_sent_rate = sim_uplink_sent_count / packet_count
    sim_uplink_received_rate = sim_uplink_received_count / sim_uplink_sent_count
    if sim_uplink_sent_time > 0:
        sim_uplink_throughput = sim_uplink_received_count * packet_size / sim_uplink_sent_time
    else:
        sim_uplink_throughput = 0

    client.publish("/result", f"current_test,{current_test},sim_uplink_sent_rate,{sim_uplink_sent_rate}")
    client.publish("/result", f"current_test,{current_test},sim_uplink_received_rate,{sim_uplink_received_rate}")
    client.publish("/result", f"current_test,{current_test},sim_uplink_throughput,{sim_uplink_throughput}")
    results["sim_uplink_sent_rate"].append(sim_uplink_sent_rate)
    results["sim_uplink_received_rate"].append(sim_uplink_received_rate)
    results["sim_uplink_throughput"].append(sim_uplink_throughput)
    sim_uplink_calculated = True
    if act_uplink_calculated:
        sim_uplink_calculated = False
        act_uplink_calculated = False
        # client.publish("/control", "PC Ready for Next Test")
        # next_test(client)
        client.publish("/control", "PC is about to test RTT")
        current_phase = 3


def calculate_act_uplink_metrics(client):
    global act_uplink_sent_count, act_uplink_sent_time, act_uplink_received_count, packet_count, packet_size
    global sim_uplink_calculated, act_uplink_calculated
    global current_phase, current_test
    act_uplink_sent_rate = act_uplink_sent_count / packet_count
    act_uplink_received_rate = act_uplink_received_count / act_uplink_sent_count
    if act_uplink_sent_time > 0:
        act_uplink_throughput = act_uplink_received_count * packet_size / act_uplink_sent_time
    else:
        act_uplink_throughput = 0

    client.publish("/result", f"current_test,{current_test},act_uplink_sent_rate,{act_uplink_sent_rate}")
    client.publish("/result", f"current_test,{current_test},act_uplink_received_rate,{act_uplink_received_rate}")
    client.publish("/result", f"current_test,{current_test},act_uplink_throughput,{act_uplink_throughput}")
    results["act_uplink_sent_rate"].append(act_uplink_sent_rate)
    results["act_uplink_received_rate"].append(act_uplink_received_rate)
    results["act_uplink_throughput"].append(act_uplink_throughput)
    act_uplink_calculated = True
    if sim_uplink_calculated:
        sim_uplink_calculated = False
        act_uplink_calculated = False
        # client.publish("/control", "PC Ready for Next Test")
        # next_test(client)
        client.publish("/control", "PC is about to test RTT")
        current_phase = 3


def send_rtt_packets(client):
    global packet_size, rtt_timeout_timer, current_rtt_id, timeout_triggered
    timestamp = int(time.time() * 1000)
    current_rtt_id += 1
    padding = 'p' * (packet_size - 13 - len(str(current_rtt_id)))
    message = f"{timestamp},{current_rtt_id},{padding}"
    client.publish("/uplink/pc", message)
    # sim_uplink_sent_time = timestamp
    if rtt_timeout_timer is not None:
        rtt_timeout_timer.cancel()
    timeout_triggered = False
    rtt_timeout_timer = threading.Timer(timeout, handle_rtt_timeout, [client])
    rtt_timeout_timer.start()


def handle_rtt_timeout(client):
    global rtt_timeout_timer, timeout_triggered, sim_rtt_values, sim_rtt_received_count
    if timeout_triggered:
        return
    timeout_triggered = True
    print("RTT message timeout")
    sim_rtt_received_count += 1
    if sim_rtt_received_count < packet_count:
        send_rtt_packets(client)


# else:
#     average_rtt = sum(sim_rtt_values) / len(sim_rtt_values)
#     client.publish("/result", f"sim RTT values: {sim_rtt_values}")
#     client.publish("/result", f"sim Average RTT: {average_rtt}")
#     client.publish("/control", "PC Ready for Next Test")


def next_test():
    global current_test, repeat_count, repeat_interval, current_phase, downlink_timer
    global sim_uplink_sent_count, sim_downlink_received_count, current_rtt_id, sim_rtt_values
    global act_downlink_sent_count_received, act_downlink_received_count_received, act_downlink_received_time_received, \
        act_uplink_sent_count_received, act_uplink_sent_time_received, act_uplink_received_count_received, \
        act_downlink_calculated, sim_downlink_calculated, sim_uplink_calculated, act_uplink_calculated
    global sim_rtt_received_count
    current_test += 1
    if current_test < repeat_count:
        sim_downlink_received_count = 0
        sim_uplink_sent_count = 0
        current_phase = 1
        current_rtt_id = 0
        sim_rtt_values = []
        sim_rtt_received_count = 0
        act_downlink_sent_count_received = False
        act_downlink_received_count_received = False
        act_downlink_received_time_received = False
        act_uplink_sent_count_received = False
        act_uplink_sent_time_received = False
        act_uplink_received_count_received = False
        act_downlink_calculated = False
        sim_downlink_calculated = False
        sim_uplink_calculated = False
        act_uplink_calculated = False
        downlink_timer = None
        time.sleep(repeat_interval)
    else:
        print("Experiment completed.")
        visualize_results(results)


def visualize_results(results):
    """
    Visualize the results published to the /result topic.

    Args:
        results (dict): A dictionary containing all the results with keys as the metric names
                        and values as lists of metric values for each test.
    """
    # Create subplots for the combined metrics
    combined_metrics = [("sim_downlink_throughput", "act_downlink_throughput"),
                        ("sim_uplink_throughput", "act_uplink_throughput"),
                        ("sim_average_rtt", "act_average_rtt")]

    individual_metrics = ["sim_downlink_received_rate", "sim_uplink_sent_rate", "sim_uplink_received_rate",
                          "act_downlink_received_rate", "act_uplink_sent_rate", "act_uplink_received_rate"]

    num_plots = len(combined_metrics) + len(individual_metrics)

    fig, axs = plt.subplots(num_plots, 1, figsize=(10, 5 * num_plots))

    # Plot combined metrics
    for i, (sim_metric, act_metric) in enumerate(combined_metrics):
        axs[i].plot(range(1, len(results[sim_metric]) + 1), results[sim_metric], marker='o', linestyle='-',
                    label=sim_metric, color='tab:blue')
        axs[i].plot(range(1, len(results[act_metric]) + 1), results[act_metric], marker='o', linestyle='-',
                    label=act_metric, color='tab:orange')
        axs[i].set_title(f'{sim_metric} and {act_metric} over tests')
        axs[i].set_xlabel('Test Number')
        axs[i].set_ylabel('Value')
        axs[i].grid(True)
        axs[i].legend()
        axs[i].xaxis.set_major_locator(MaxNLocator(integer=True))

    # Plot individual metrics
    for i, metric in enumerate(individual_metrics, start=len(combined_metrics)):
        axs[i].plot(range(1, len(results[metric]) + 1), results[metric], marker='o', linestyle='-', label=metric,
                    color='tab:blue' if 'sim' in metric else 'tab:orange')
        axs[i].set_title(f'{metric} over tests')
        axs[i].set_xlabel('Test Number')
        axs[i].set_ylabel(metric)
        axs[i].grid(True)
        axs[i].legend()
        axs[i].xaxis.set_major_locator(MaxNLocator(integer=True))

    plt.tight_layout()
    plt.show()


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(broker_address, 1883, 60)

    client.loop_start()

    print("PC is ready for the experiment.")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
