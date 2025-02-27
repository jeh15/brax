# Copyright 2023 The Brax Authors.
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

# pylint:disable=g-multiple-import
"""Physics pipeline for generalized coordinates engine."""

from brax import actuator
from brax import geometry
from brax import kinematics
from brax.base import System
from brax.generalized import constraint
from brax.generalized import dynamics
from brax.generalized import integrator
from brax.generalized import mass
from brax.generalized.base import State
from jax.lax import stop_gradient
from jax import numpy as jp


def init(
    sys: System, q: jp.ndarray, qd: jp.ndarray, debug: bool = False
) -> State:
  """Initializes physics state.

  Args:
    sys: a brax system
    q: (q_size,) joint angle vector
    qd: (qd_size,) joint velocity vector
    debug: if True, adds contact to the state for debugging

  Returns:
    state: initial physics state
  """
  x, xd = kinematics.forward(sys, q, qd)
  state = State.init(q, qd, x, xd)  # pytype: disable=wrong-arg-types  # jax-ndarray
  state = dynamics.transform_com(sys, state)
  state = mass.matrix_inv(sys, state, 0)
  state = constraint.jacobian(sys, state)
  if debug:
    state = state.replace(contact=geometry.contact(sys, state.x))

  return state


def step(
    sys: System, state: State, act: jp.ndarray, debug: bool = False
) -> State:
  """Performs a physics step.

  Args:
    sys: a brax system
    state: physics state prior to step
    act: (act_size,) actuator input vector
    debug: if True, adds contact to the state for debugging

  Returns:
    state: physics state after step
  """
  # calculate acceleration terms
  tau = actuator.to_tau(sys, act, state.q, state.qd)
  state = state.replace(qf_smooth=dynamics.forward(sys, state, tau))
  state = state.replace(qf_constraint=stop_gradient(constraint.force(sys, state)))

  # update position/velocity level terms
  state = integrator.integrate(sys, state)
  x, xd = kinematics.forward(sys, state.q, state.qd)
  state = state.replace(x=x, xd=xd)
  state = dynamics.transform_com(sys, state)
  state = mass.matrix_inv(sys, state, sys.matrix_inv_iterations)
  state = constraint.jacobian(sys, state)

  if debug:
    state = state.replace(contact=geometry.contact(sys, state.x))

  return state
