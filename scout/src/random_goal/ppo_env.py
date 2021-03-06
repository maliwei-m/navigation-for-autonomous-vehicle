import rospy
from scout.msg import RL_input_msgs
from geometry_msgs.msg import Twist
from vlp_fir.msg import obs_info
from gazebo_msgs.msg import ContactsState
from visualization_msgs.msg import Marker
from std_msgs.msg import Int16MultiArray
from std_msgs.msg import Int16MultiArray

from gazebo_msgs.msg import *
from gazebo_msgs.srv import *

import threading

import tensorflow as tf
import numpy as np
import random
import math
import os

import subprocess

real_env = 0
goal = [(-6,-7),(-6,3),(-1,5),(3,-8)]

class env(object):

    def __init__(self):
        self.limit_v = 1.5
        self.limit_w = 0.785

        self.reach_goal_circle = 0.6
    
    def gazebo_srv(self):
        subprocess.Popen(['rosservice','call','/gazebo/set_model_state', '{model_state: { model_name: goal1, pose: { position: { x: %i, y: %i ,z: 1 }, orientation: {x: 0, y: 0, z: 0, w: 0 } }, twist: { linear: {x: 0.0 , y: 0 ,z: 0 } , angular: { x: 0.0 , y: 0 , z: 0.0 } } , reference_frame: world } }' %(self.goal_x, self.goal_y)])

        # gazebo_goal_msg = ModelState()
        # gazebo_goal_msg.model_name = 'goal'
        # gazebo_goal_msg.pose.position.x = self.goal_x
        # gazebo_goal_msg.pose.position.y = self.goal_y
        # gazebo_goal_msg.pose.position.z = 1
        # gazebo_goal_msg.pose.orientation.x = 0
        # gazebo_goal_msg.pose.orientation.y = 0
        # gazebo_goal_msg.pose.orientation.z = 0
        # gazebo_goal_msg.pose.orientation.w = 0
        # gazebo_goal_msg.reference_frame = 'world'


        # gazebo_goal_msg1 = LinkState()
        # gazebo_goal_msg1.link_name = 'goal::goal'
        # gazebo_goal_msg1.pose.position.x = self.goal_x
        # gazebo_goal_msg1.pose.position.y = self.goal_y
        # gazebo_goal_msg1.pose.position.z = 1
        # gazebo_goal_msg1.pose.orientation.x = 0
        # gazebo_goal_msg1.pose.orientation.y = 0
        # gazebo_goal_msg1.pose.orientation.z = 0
        # gazebo_goal_msg1.pose.orientation.w = 0

        # rospy.wait_for_service('/gazebo/set_model_state')
        # rospy.wait_for_service('/gazebo/set_link_state')

        # gazebo_goal_proxy = rospy.ServiceProxy('/gazebo/set_model_state', SetModelState)
        # rep = gazebo_goal_proxy(gazebo_goal_msg)

        # gazebo_goal_proxy1 = rospy.ServiceProxy('/gazebo/set_link_state', SetLinkState)
        # rep2 = gazebo_goal_proxy1(gazebo_goal_msg1)
        
    def choose_goal(self, goal_index):
        self.goal_x = goal[goal_index][0]
        self.goal_y = goal[goal_index][1]

    def set_action(self, action):
        # set publisher
        pub = rospy.Publisher('cmd_vel', Twist, queue_size=10)
        pub_msg = Twist()
        # print(action)
        
        # clip action
        action[0] = np.clip(action[0], -self.limit_v, self.limit_v)

        action[1] = action[1] * (0.785/1.5)
        action[1] = np.clip(action[1], -self.limit_w, self.limit_w)


        # publish action
        if not np.isnan(action[0]) or np.isnan(action[1]):
            pub_msg.linear.x = action[0]
            pub_msg.angular.z = action[1]
            pub.publish(pub_msg)
        else:
            print('Warning: Action is NAN')
        return action

    def get_robot_info(self):
        data = rospy.wait_for_message('RLin', RL_input_msgs)
        current_state_info = np.array([data.me_x, data.me_y, data.me_yaw, data.me_v, data.me_w])
        return current_state_info
    
    def get_obs_info(self):

        data = rospy.wait_for_message('obj_', obs_info)
        ## simple application
        if real_env == 1:
            current_obs_info = np.empty([1,4])
            for i in range(data.num):
                iobs = [data.x[i], data.y[i], data.len[i], data.width[i]]
                current_obs_info = np.vstack([current_obs_info, iobs])
            current_obs_info = np.delete(current_obs_info, 0, 0)

            if data.num < 5:
                add_obs = np.zeros([5-data.num, 4])
                current_obs_info = np.concatenate([current_obs_info, add_obs])
            return current_obs_info

        else:
            current_obs_info = np.array([
                [5,3,0.5,0.5],
                [-2,-4,0.5,0.5],
                [-4,5,0.5,0.5],
                [3,-3,0.5,0.5],
                [-7,-1,0.5,0.5],
                [-2,3,0.5,0.5]
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

        current_dis_from_ori = np.linalg.norm(vec_current_point)

        return current_dis_from_des_point, current_dis_from_ori
    
    def choose_obs(self, car_info, obs_info):
        dis_obs_list = dict()

        # calculate distance between obstacle and car
        for i in range (np.shape(obs_info)[0]):
            obs_x = obs_info[i][0]
            obs_y = obs_info[i][1]
            dis_x = car_info[0] - obs_x
            dis_y = car_info[1] - obs_y
            dis_obs = math.hypot(dis_x, dis_y)
            dis_obs = np.clip(dis_obs, 1e-2, 1e+2)
            if obs_info[i][2] == 0 and obs_info[i][3] == 0:
                dis_cul = 0
            else:
                dis_cul = 1 / dis_obs
            dis_obs_list[i] = dis_cul

        # sort distance obstacle index
        dis_obs_order = sorted(dis_obs_list.items(), key=lambda x:x[1])
        dis_obs_order_list = list(dis_obs_order)
        dis_index = [dis_obs_order_list[-1][0], dis_obs_order_list[-2][0], dis_obs_order_list[-3][0], dis_obs_order_list[-4][0], dis_obs_order_list[-5][0]]
        
        return dis_index
    
    def compute_u(self, car_info, obs_state, goal_state):
        
        # param
        n_goal = 1
        n_obs = 30

        safe_dis = 2
        car_circle = 1.1

        obs_len = obs_state[2]
        obs_wid = obs_state[3]

        # calculate safe range
        q = (0.5 + car_circle)/2 + safe_dis

        # calculate distance between car and obstacle
        dis_obs_x = obs_state[0] - car_info[0]
        dis_obs_y = obs_state[1] - car_info[1]
        dis_obs = math.hypot(dis_obs_x, dis_obs_y)

        # calculate orientation between car and obstacle
        # Attention: relative dis
        if dis_obs_x > 0:
            ori_obs = math.atan(dis_obs_y / dis_obs_x)
        elif dis_obs_x < 0 and dis_obs_y > 0:
            ori_obs = math.atan(dis_obs_y/dis_obs_x) + 3.14
        elif dis_obs_x < 0 and dis_obs_y < 0:
            ori_obs = math.atan(dis_obs_y/dis_obs_x) - 3.14

        # calculate distance between car and goal
        dis_goal_x = goal_state[0] - car_info[0]
        dis_goal_y = goal_state[1] - car_info[1]
        dis_goal = math.hypot(dis_goal_x, dis_goal_y)

        # calculate orientation between car and goal
        if dis_goal_x > 0:
            ori_goal = math.atan(dis_goal_y / dis_goal_x)
        elif dis_goal_x < 0 and dis_goal_y > 0:
            ori_goal = math.atan(dis_goal_y / dis_goal_x) + 3.14
        elif dis_goal_x < 0 and dis_goal_y < 0:
            ori_goal = math.atan(dis_goal_y / dis_goal_x) - 3.14

        # calculate repulsion potential energe
        if dis_obs > q or max(obs_len, obs_wid) == 0:
            ur = 0
        else:
            dis_obs = np.clip(dis_obs, (0.5 + car_circle)/2, 1e3)
            ur = n_obs * pow(1/dis_obs - 1/q, 2)
        ur = np.clip(ur, 0, 20)
        
        # calculate attraction potential energe
        ua = n_goal * dis_goal

        u_state = ur + ua

        # ori
        dis_ori = math.hypot(car_info[0], car_info[1])

        return u_state, dis_goal, dis_obs, dis_ori, ori_obs, ori_goal
    
    def compute_state(self):
        # get car state and obstacles state
        current_state_info = self.get_robot_info()
        current_obs_info = self.get_obs_info()

        # car state
        car_state = current_state_info
        # goal state
        goal_state = np.array([self.goal_x, self.goal_y])

        # get computed state
        obs_index = self.choose_obs(current_state_info, current_obs_info)
        min_obs_state = current_obs_info[obs_index[0]]
        u_state, dis_goal_state, dis_obs_state, dis_ori, ori_obs, ori_goal = self.compute_u(car_state, min_obs_state, goal_state)

        # end loop state
        collide = self.get_collision_info()

        if real_env == 1:
            obs0_state = current_obs_info[obs_index[0]]
            obs1_state = current_obs_info[obs_index[1]]
            obs2_state = current_obs_info[obs_index[2]]
            obs3_state = current_obs_info[obs_index[3]]
            obs4_state = current_obs_info[obs_index[4]]
            state = np.concatenate([goal_state, car_state, obs0_state, obs1_state, obs2_state, obs3_state, obs4_state, [u_state], [dis_goal_state], [dis_obs_state], [dis_ori], [ori_obs], [ori_goal], [collide]])
        else:
            obs0_state = current_obs_info[obs_index[0]]
            obs1_state = current_obs_info[obs_index[1]]
            obs2_state = current_obs_info[obs_index[2]]
            obs3_state = current_obs_info[obs_index[3]]
            obs4_state = current_obs_info[obs_index[4]]
            state = np.concatenate([goal_state, car_state, obs0_state, obs1_state, obs2_state, obs3_state, obs4_state, [u_state], [dis_goal_state], [dis_obs_state], [dis_ori], [ori_obs], [ori_goal], [collide]])

        return state

    def compute_reward(self, collide, current_dis_from_des_point, current_dis_from_ori, d_u):

        norm = np.array([d_u, 1, -1])
        if d_u > 0:
            norm_d_u = (d_u - np.min(norm)) / (np.max(norm) - np.min(norm))
        else:
            norm_d_u = - (d_u - np.max(norm)) / (np.min(norm) - np.max(norm))
        reward = norm_d_u / 20

        reward += -0.005

        if collide == 1:
            reward += -1

        if current_dis_from_des_point < self.reach_goal_circle:
            reward += 2

        if current_dis_from_ori > 12:
            reward += -1
            
        return reward

    def set_init_pose(self):
        self.reset_env()
        init_state = self.compute_state()
        return init_state

    def reset_env(self):
        subprocess.Popen(['rosservice','call','/gazebo/reset_world'])
        # self.gazebo_srv()
    
    def reset_sim(self):
        subprocess.Popen(['rosservice','call','/gazebo/reset_simulation'])
        # self.gazebo_srv()
