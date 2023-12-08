from gymnasium import Env
from gymnasium.spaces import Box, Discrete
import numpy as np
import random
import math
from src.display import Display
import time

class DroneEnv(Env):
    def __init__(self, config: dict, render_mode = None):
        self.motors = config["drone"]["motors"]
        self.mass = config["drone"]["mass"]
        self.inertia = config["drone"]["inertia"]
        self.thrust = config["drone"]["thrust"]
        self.gravity = config["drone"]["gravity"]

        self.update_frequency = config["display"]["update_frequency"]
        self.dt = 1 / self.update_frequency

        self.target = {
            "x": config["target"]["x"],
            "y": config["target"]["y"],
            "distance": config["target"]["distance"]
        }

        # Action space is 2 motors, each either 0 or 1
        # DQN can only handle discrete action spaces
        # Every action (both motors off, both on, left on, right on) is a discrete value
        self.action_space = Discrete(2 ** len(self.motors))

        # State space is 6 values: x, vx, y, vy, theta, omega
        # x and y are limited between -1, 1
        # vx and vy are velocities and limited between -5, 5
        # theta is rotation and limited between -pi, pi
        # omega is angular velocity and limited between -10, 10
        self.observation_space = Box(
            low=np.array([-1, -5, -1, -5, -np.pi, -10]),
            high=np.array([1, 5, 1, 5, np.pi, 10]),
            dtype=np.float32
        )

        # Reset to initialize the state 
        self.reset()

        # Initialize the display
        self.render_mode = render_mode
        if(self.render_mode == "human"):
            self.display = Display(
                config=config,
                title="Drone Simulation"
            )

    def get_state(self):
        return self.state
    
    def seed(self, seed=None):
        # Set the seed
        random.seed(seed)
        # Return the seed
        return [seed]

    def reset(self, seed=None):
        # Define ranges for randomization
        position_range = 0.1
        velocity_range = 0.1
        rotation_range = 0.5
        angular_velocity_range = 0.5

        self.state = [
            random.uniform(-position_range, position_range),  # Position x
            random.uniform(-position_range, position_range),  # Position y
            random.uniform(-velocity_range, velocity_range),  # Velocity x
            random.uniform(-velocity_range, velocity_range),  # Velocity y
            random.uniform(-rotation_range, rotation_range),  # Rotation
            random.uniform(-angular_velocity_range, angular_velocity_range),  # Angular velocity
        ]

        # self.state = [
        #     0,  # Position x
        #     0,  # Position y
        #     0,  # Velocity x
        #     0,  # Velocity y
        #     0,  # Rotation
        #     0,  # Angular velocity
        # ]

        # obs must be a numpy array
        obs = np.array(self.state)
        info = {}
        return obs, info
    
    
    def render(self):
        mode = self.render_mode
        assert mode in ["human", None], "Invalid mode, must be either \"human\" or None"
        if mode == None:
            return
        elif mode == "human":
            self.display.update(self)
            #time.sleep(0.1)


    # What is type type of action?
    def step(self, action):

        # Apply motor inputs
        self._apply_action(action)
        self._apply_gravity()
        self._update_state_timestep()

        done = self._ensure_state_within_boundaries()
        reward = self._get_reward(done)

        info = {}

        return self.state, reward, done, info
    
    def _get_reward(self, done: bool):
        # Calculate reward
        if done:
            return -10
        
        # Calculate Euclidean distance from the target
        distance = np.sqrt(self.state[0] ** 2 + self.state[2] ** 2)

        distance_reward = 1 - distance / self.target["distance"]

        # if distance < 5:
        #     # Avoid division by zero and getting infinite reward
        #     distance_reward = 1
        
        # Add a constant reward for survival/progress
        #constant_reward = 0.1

        return distance_reward #+ constant_reward


    # What is type type of action?
    def _apply_action(self, action):
        # Calculate net force and torque
        net_force = np.array([0.0, 0.0])
        net_torque = 0.0

        # Get rotation angle in degrees (currently in radians)
        #rotation_angle = math.degrees(self.state[4])
        rotation_angle = self.state[4]

        # Convert discrete value to list of binary values for each motor
        action = [int(x) for x in list(bin(action)[2:].zfill(len(self.motors)))]
        #action = [1, 0]


        for i, motor in enumerate(self.motors):            
            # Calculate thrust
            thrust = action[i] * self.thrust

            # Force components in motor frame
            force_x = thrust * math.cos(math.radians(motor[2]))
            force_y = thrust * math.sin(math.radians(motor[2]))

            # Rotate the force vector by the drone's rotation angle
            rotated_force_x = force_x * math.cos(rotation_angle) - force_y * math.sin(rotation_angle)
            rotated_force_y = force_x * math.sin(rotation_angle) + force_y * math.cos(rotation_angle)

            # Update net force
            net_force += np.array([rotated_force_x, rotated_force_y])

            # Calculate the torque
            torque = motor[0] * force_y  # Only y-component of force contributes to torque
            net_torque += torque

        # Update linear motion
        acceleration = net_force / self.mass
        self.state[1] += acceleration[0] * self.dt * 0.01 # Update velocity x
        self.state[3] += acceleration[1] * self.dt * 0.01 # Update velocity y
        
        # Update rotational motion
        angular_acceleration = net_torque / self.inertia
        self.state[5] += angular_acceleration * self.dt   # Update angular velocity

    def _apply_gravity(self):
        # Apply gravity
        self.state[3] += self.gravity * 1 * self.dt
        
    
    def _ensure_state_within_boundaries(self):
        done = False
        low, high = self.observation_space.low, self.observation_space.high

        # Iterate through each element in the state
        for i in range(len(self.state)):
            # Check for lower boundary
            if self.state[i] < low[i]:
                self.state[i] = low[i]
                # Reset velocity to 0 if position is out of bounds
                if i % 2 == 0:  # Assuming even indices are positions and odd indices are velocities
                    self.state[i + 1] = 0
                done = True
            # Check for upper boundary
            elif self.state[i] > high[i]:
                self.state[i] = high[i]
                # Reset velocity to 0 if position is out of bounds
                if i % 2 == 0:  # Assuming even indices are positions and odd indices are velocities
                    self.state[i + 1] = 0
                done = True

        return done
    
    def _update_state_timestep(self):
        # Update state
        self.state[0] += self.state[1] * self.dt  # Update position x
        self.state[2] += self.state[3] * self.dt  # Update position y
        self.state[4] += self.state[5] * self.dt  # Update rotation
        
        # Ensure the rotation stays within -pi to pi
        self.state[4] = math.atan2(math.sin(self.state[4]), math.cos(self.state[4]))

    def close(self):
        # Call super class
        super().close()
        # Close the display
        if(self.render_mode == "human"):
            self.display.close()
