import rospy
from scout.msg import RL_input_msgs
from geometry_msgs.msg import Twist
from vlp_fir.msg import obs_info
from gazebo_msgs.msg import ContactsState

import tensorflow as tf
import numpy as np
import math
import os
import random

import subprocess

class env(object):

    def __init__(self):
        self.limit_v = 1.5
        self.limit_w = 0.785

        self.goal_x = 6
        self.goal_y = 6

        self.limit_circle = 12
        self.reach_goal_circle = 0.8
        self.limit_overspeed = 12
            
    def set_action(self, action):
        # set publisher
        pub = rospy.Publisher('cmd_vel', Twist, queue_size=10)
        pub_msg = Twist()
        # print(action)
        
        # clip action
        action[0] = self.limit_v * np.clip(action[0], -self.limit_v, self.limit_v)
        action[1] = self.limit_w * np.clip(action[1], -self.limit_w, self.limit_w)


        # publish action
        if not np.isnan(action[0]) or np.isnan(action[1]):
            pub_msg.linear.x = action[0]
            pub_msg.angular.z = action[1]
            pub.publish(pub_msg)
        else:
            print('Warning: Action is NAN')

    def get_robot_info(self):
        data = rospy.wait_for_message('RLin', RL_input_msgs)
        current_state_info = np.array([data.me_x, data.me_y, data.me_yaw, data.me_v, data.me_w])
        return current_state_info
    
    def get_obs_info(self):
        data = rospy.wait_for_message('obj_', obs_info)
        if data.num >= 3:
            current_obs_info = np.array([
                data.x[0], data.y[0], data.len[0], data.width[0],
                data.x[1], data.y[1], data.len[1], data.width[1],
                data.x[2], data.y[2], data.len[2], data.width[2],
            ])
        elif data.num == 2:
            current_obs_info = np.array([
                data.x[0], data.y[0], data.len[0], data.width[0],
                data.x[1], data.y[1], data.len[1], data.width[1],
                0, 0, 0, 0,
            ])
        elif data.num == 1:
            current_obs_info = np.array([
                data.x[0], data.y[0], data.len[0], data.width[0],
                0, 0, 0, 0,
                0, 0, 0, 0,
            ])
        elif data.num == 0:
            current_obs_info = np.array([
                0, 0, 0, 0,
                0, 0, 0, 0,
                0, 0, 0, 0,
            ])
        
        return current_obs_info
    
    def get_collision_info(self):
        data = rospy.wait_for_message('bumper', ContactsState)
        if len(data.states):
            collide = 1
        else:
            collide = 0
        return collide

    def compute_param(self):
        current_state_info = self.get_robot_info()

        vec_current_point = np.array([current_state_info[0], current_state_info[1]])
        vec_des_point = np.array([self.goal_x, self.goal_y])
        current_dis_from_des_point = np.linalg.norm(vec_des_point - vec_current_point)

        over_v = abs(current_state_info[3]) - self.limit_v
        over_w = abs(current_state_info[4]) - self.limit_w
        overspeed = math.hypot(over_v, over_w)

        return overspeed, current_dis_from_des_point
    
    def compute_state(self):
        current_state_info = self.get_robot_info()
        
        disturb_x = random.uniform(-1,1)
        disturb_y = random.uniform(-1,1)

        current_state_info[0] += disturb_x
        current_state_info[1] += disturb_y

        current_obs_info = self.get_obs_info()

        # compute state
        state = np.concatenate([current_state_info, current_obs_info])
        return state
    
    def compute_reward(self, collide, overspeed, current_dis_from_des_point, n):

        reward = 0

        if collide == 1:
            reward += -1

        if n == 1 and current_dis_from_des_point < self.reach_goal_circle:
            reward += 2
        elif n == 1 and current_dis_from_des_point > self.reach_goal_circle:
            reward += -1

        if current_dis_from_des_point > self.limit_circle:
            reward += -1
            
        return reward

    def set_init_pose(self):
        self.reset_env()
        init_state = self.compute_state()
        return init_state

    def reset_env(self):
        subprocess.Popen(['rosservice','call','/gazebo/reset_world'])