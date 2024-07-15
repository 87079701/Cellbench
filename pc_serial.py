import serial
import time
import json
import threading
import re
# 串口配置
ser = serial.Serial(
    port='COM5',  # 更改为实际的COM端口
    baudrate=115200,
    timeout=1
)

# MQTT broker配置
mqtt_broker = "47.103.78.49"
mqtt_port = 1883
mqtt_client_id = "device_id"
mqtt_user = "username"
mqtt_passwd = "password"
mqtt_keepalive = 60

act_downlink_received_count = 0
act_downlink_received_time = 0
act_downlink_latest_received_time = 0
act_uplink_sent_count = 0
act_uplink_sent_time = 0
act_uplink_received_count = 0
act_downlink_sent_count = 0

current_phase = 1
current_test = 0
start_time = 0

downlink_timer = None
timeout_triggered = False
rtt_timeout_triggered = False
rtt_timeout_timer = None
current_rtt_id = 0
act_rtt_received_count = 0
average_rtt = 0
act_rtt_values = []

packet_count = 30  # Example value, replace with actual
packet_size = 128  # Example value, replace with actual
repeat_count = 2  # Example value, replace with actual
repeat_interval = 5  # Example value, replace with actual
timeout = 10  # Example value, replace with actual
retrans_count = 3  # Example value, replace with actual
module = "TestModule"  # Example value, replace with actual
operator = "TestOperator"  # Example value, replace with actual


# AT命令
def send_at_command(command, wait_for="OK", timeout=10):
    ser.reset_output_buffer()  # 清空发送缓冲区
    ser.write((command + "\r\n").encode())
    end_time = time.time() + timeout
    response = ""
    while time.time() < end_time:
        if ser.in_waiting > 0:
            try:
                response += ser.read(ser.in_waiting).decode()
            except UnicodeDecodeError:
                return
            if wait_for in response:
                break
    return response


def reset_downlink_timer():
    global downlink_timer, timeout, timeout_triggered
    if downlink_timer is not None:
        downlink_timer.cancel()
    downlink_timer = threading.Timer(timeout, handle_downlink_timeout)
    timeout_triggered = False
    downlink_timer.start()


def handle_downlink_timeout():
    global act_downlink_received_time, act_downlink_received_count, start_time, current_phase, downlink_timer, \
        act_downlink_latest_received_time, timeout_triggered
    if timeout_triggered:
        return
    timeout_triggered = True
    act_downlink_received_time = act_downlink_latest_received_time - start_time
    publish_mqtt("/result/step2", f"act_downlink_received_count,{act_downlink_received_count}")
    publish_mqtt("/result/step2", f"act_downlink_received_time,{act_downlink_received_time}")
    current_phase = 2
    # publish_mqtt("/control", "Device is about to send uplink messages")


def configure_mqtt():
    send_at_command('AT')
    send_at_command('AT+QMTCFG="recv/mode",0,0,1')
    send_at_command('AT+QMTCFG="send/mode",0,0')
    send_at_command('AT+QMTCFG="session",0,0')
    time.sleep(1)
    send_at_command('AT+QMTOPEN=0,"47.103.78.49",1883', wait_for="+QMTOPEN: 0,0")
    time.sleep(1)
    send_at_command('AT+QMTCONN=0,"clientExample"', wait_for="+QMTCONN: 0,0,0")
    time.sleep(1)
    send_at_command('AT+QMTSUB=0,1,"/control",0', wait_for="+QMTSUB: 0,1,0,0")
    #  send_at_command('AT+QMTSUB=0,2,"/uplink/device",0', wait_for="+QMTSUB: 0,2,0,0")
    send_at_command('AT+QMTSUB=0,2,"/downlink/device",0', wait_for="+QMTSUB: 0,2,0,0")


def publish_mqtt(topic, message):
    msg_len = len(message)
    send_at_command(f'AT+QMTPUBEX=0,0,0,0,"{topic}",{msg_len}', wait_for=">")
    send_at_command(f'{message}', wait_for="+QMTPUBEX: 0,0,0")


def main():
    global current_phase, act_rtt_received_count, rtt_timeout_triggered
    configure_mqtt()
    time.sleep(3)
    # 发送启动消息到 /config 话题
    experiment_parameters = {
        "Packet_count": packet_count, "Packet_size": packet_size, "Repeat_count": repeat_count,
        "Repeat_interval": repeat_interval, "Timeout": timeout,
        "Retrans_count": retrans_count, "Module": module, "Operator": operator
    }
    experiment_parameters_json = json.dumps(experiment_parameters)
    publish_mqtt("/config", experiment_parameters_json)
    publish_mqtt("/control", "Experiment Start")
    # 进入等待循环，处理来自MQTT服务器的消息
    while True:
        try:
            response = ser.readline().decode().strip()
        except UnicodeDecodeError:
            print("Decode error:Skipping current message")
            ser.reset_input_buffer()
            continue
        if response:
            print(f"Received: {response}")
            # 处理不同的话题消息
            if "/control" in response:
                if "PC uplink receiving over" in response:
                    publish_mqtt("/control", "Device is about to send uplink messages")
                    current_phase = 3
                elif "Ready for Device messages" in response and current_phase == 3:
                    send_uplink_packets()
                    current_phase = 4
                    #publish_mqtt("/control", "Device Ready for Next Test")
                    #next_test()
                elif "PC RTT Test Over" in response and current_phase == 4:
                    publish_mqtt("/control", "Device is about to test RTT")
                elif "Ready for Device RTT" in response and current_phase == 4:
                    send_rtt_packets()
            elif "/downlink/device" in response and current_phase == 1:
                handle_downlink_message()
            elif "/downlink/device" in response and current_phase == 4:
                match = re.search(r'"(\d+),(\d+),', response)
                if not match:
                    send_rtt_packets()  # 数据无效，发送下一个RTT消息
                    return
                try:
                    timestamp = int(match.group(1))
                    rtt_id = int(match.group(2))
                except ValueError:
                    send_rtt_packets()  # 数据无效，发送下一个RTT消息
                    return
                if rtt_id == current_rtt_id:
                    act_rtt = int(time.time() * 1000) - timestamp
                    act_rtt_values.append(act_rtt)
                    act_rtt_received_count += 1
                    if act_rtt_received_count < packet_count:
                        send_rtt_packets()
                    else:
                        rtt_timeout_triggered = True
                        average_rtt = sum(act_rtt_values) / len(act_rtt_values)
                        publish_mqtt("/result", f"act RTT values: {act_rtt_values}")
                        publish_mqtt("/result", f"Average act RTT: {average_rtt}")
                        publish_mqtt("/control", "Device Ready for Next Test")
                        next_test()
            else:
                ser.reset_input_buffer()
                ser.reset_output_buffer()


def handle_downlink_message():
    global act_downlink_received_count, act_downlink_received_time, start_time, act_downlink_latest_received_time
    act_downlink_received_count += 1
    act_downlink_latest_received_time = time.time()
    if act_downlink_received_count == 1:
        start_time = time.time()
    elif act_downlink_received_count == packet_count:
        handle_downlink_timeout()
    else:
        reset_downlink_timer()


def send_uplink_packets():
    global act_uplink_sent_count, act_uplink_sent_time, packet_count, packet_size
    act_uplink_sent_count = 0
    act_uplink_sent_time = time.time()
    for i in range(packet_count):
        publish_mqtt("/uplink/device", "d" * packet_size)
        act_uplink_sent_count += 1
    act_uplink_sent_time = time.time() - act_uplink_sent_time
    publish_mqtt("/result/step3", f"act_uplink_sent_count,{act_uplink_sent_count}")
    publish_mqtt("/result/step3", f"act_uplink_sent_time,{act_uplink_sent_time}")


def send_rtt_packets():
    global packet_size, rtt_timeout_timer, current_rtt_id, rtt_timeout_triggered
    timestamp = int(time.time() * 1000)
    current_rtt_id += 1
    padding = 'p' * (packet_size - 13 - len(str(current_rtt_id))-2)
    message = f"{timestamp},{current_rtt_id},{padding}"
    publish_mqtt("/uplink/device", message)
    # sim_uplink_sent_time = timestamp
    # if rtt_timeout_timer is not None:
    #    rtt_timeout_timer.cancel()
    rtt_timeout_triggered = False
    rtt_timeout_timer = threading.Timer(timeout, handle_rtt_timeout)
    rtt_timeout_timer.start()


def handle_rtt_timeout():
    global rtt_timeout_timer, rtt_timeout_triggered, act_rtt_values, act_rtt_received_count
    if rtt_timeout_triggered:
        return
    rtt_timeout_triggered = True
    print("RTT message timeout")
    act_rtt_received_count += 1
    if act_rtt_received_count < packet_count:
        send_rtt_packets()
    else:
        average_rtt = sum(act_rtt_values) / len(act_rtt_values)
        publish_mqtt("/result", f"RTT values: {act_rtt_values}")
        publish_mqtt("/result", f"Average RTT: {average_rtt}")
        publish_mqtt("/control", "PC Ready for Next Test")


def next_test():
    global current_test, repeat_count, repeat_interval, current_phase, act_rtt_values
    global act_downlink_received_count, act_uplink_sent_count, downlink_timer
    global current_rtt_id, act_rtt_received_count
    current_test += 1
    if current_test < repeat_count:
        print(f"Device Starting test {current_test + 1}")
        act_downlink_received_count = 0
        act_uplink_sent_count = 0
        current_phase = 1
        downlink_timer = None
        current_rtt_id = 0
        act_rtt_received_count = 0
        act_rtt_values = []
        time.sleep(repeat_interval)
    else:
        print("Experiment completed.")
        current_phase = 0


if __name__ == "__main__":
    main()
