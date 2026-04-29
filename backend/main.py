"""
Bus Tracking & Alert System - FastAPI Backend
7 buses on the Tumkur-Bangalore highway route in India.
Real-time tracking with proximity alerts (5-10 km) and admin controls.
"""

import asyncio
import json
import math
import random
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Set, Tuple
from datetime import datetime
from enum import Enum
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# ============================================================================
# TUMKUR-BANGALORE HIGHWAY ROUTE WAYPOINTS (NH48)
# ============================================================================

# Highway NH48 from Tumkur to Bangalore - correct coordinates following the actual road
# Latitude decreases (south) and Longitude increases (east) as we go from Tumkur to Bangalore
HIGHWAY_WAYPOINTS = [
    # Tumkur (start)
    (13.3426, 77.1023),
    (13.3300, 77.1200),
    (13.3150, 77.1450),
    (13.2980, 77.1700),
    (13.2800, 77.1950),
    (13.2600, 77.2200),
    (13.2350, 77.2450),
    (13.2100, 77.2700),
    (13.1850, 77.2950),
    (13.1600, 77.3200),
    (13.1350, 77.3450),
    (13.1100, 77.3700),
    (13.0900, 77.3950),
    (13.0700, 77.4200),
    (13.0500, 77.4450),
    (13.0300, 77.4700),
    (13.0100, 77.4950),
    (12.9950, 77.5200),
    (12.9800, 77.5450),
    # Bangalore (end)
    (12.9716, 77.5946),
]

# ============================================================================
# DATA STRUCTURES
# ============================================================================

class BusStatus(str, Enum):
    """Bus operational status."""
    IDLE = "idle"
    MOVING = "moving"
    BOARDING = "boarding"
    STOPPED = "stopped"
    ALERT = "alert"


@dataclass
class Location:
    """GPS location."""
    latitude: float
    longitude: float
    
    def distance_to(self, other: 'Location') -> float:
        """Calculate distance in km using Haversine formula."""
        R = 6371  # Earth radius in km
        dlat = math.radians(other.latitude - self.latitude)
        dlon = math.radians(other.longitude - self.longitude)
        a = (math.sin(dlat/2) ** 2 + 
             math.cos(math.radians(self.latitude)) * math.cos(math.radians(other.latitude)) * 
             math.sin(dlon/2) ** 2)
        c = 2 * math.asin(math.sqrt(a))
        return R * c


@dataclass
class Bus:
    """Represents a single bus with GPS coordinates."""
    id: str
    name: str
    latitude: float
    longitude: float
    destination_lat: float
    destination_lon: float
    status: str
    speed: float  # km/h
    heading: float  # degrees
    alert_level: str  # "none", "warning", "critical"
    closest_bus_id: str
    closest_distance_km: float
    waypoint_index: int  # Current waypoint index on the route
    progress_on_segment: float  # Progress from 0 to 1 on current waypoint
    current_route: list = field(default=None)  # Current route waypoints
    alternative_routes: list = field(default=None)  # List of alternative route options
    
    def current_location(self) -> Location:
        return Location(self.latitude, self.longitude)
    
    def destination_location(self) -> Location:
        return Location(self.destination_lat, self.destination_lon)


# ============================================================================
# SIMULATION STATE & CONFIGURATION
# ============================================================================

class SimulationState:
    """Manages the global state of the bus system."""
    
    def __init__(self):
        # Configuration
        self.NUM_BUSES = 5
        self.BASE_SPEED = 250  # km/h - very fast for demo
        self.BOARDING_TIME = 2  # seconds
        self.TICK_INTERVAL = 1.0  # seconds
        
        # Proximity alert thresholds (km)
        self.ALERT_CRITICAL = 5.0  # Critical: < 5 km
        self.ALERT_WARNING = 10.0  # Warning: 5-10 km
        
        # Route waypoints
        self.route_waypoints = HIGHWAY_WAYPOINTS
        
        # Event log
        self.event_log: List[str] = []
        self.max_log_size = 50
        
        # Initialize buses on the route
        self.buses: Dict[str, Bus] = {}
        self._initialize_buses()
        
        self.last_dispatch_time = None  # Will be set on first tick
        self.dispatch_interval = 15  # seconds between dispatching new buses
        
        # Admin controls state
        self.admin_mode_active = False
        self.manual_stop_bus_id: str = None
    
    def _initialize_buses(self):
        """Initialize all buses at the starting point in an idle state."""
        colors = ["🔴", "🟡", "🟢", "🔵", "🟣"]
        names = ["Express A", "Local B", "Rapid C", "City D", "Route E"]
        start_waypoint = self.route_waypoints[0]
        next_waypoint = self.route_waypoints[1]

        for i in range(self.NUM_BUSES):
            bus_id = f"bus_{i+1}"
            self.buses[bus_id] = Bus(
                id=bus_id,
                name=f"{colors[i]} {names[i]}",
                latitude=start_waypoint[0],
                longitude=start_waypoint[1],
                destination_lat=next_waypoint[0],
                destination_lon=next_waypoint[1],
                status=BusStatus.IDLE, # Start as IDLE
                speed=0,
                heading=0.0,
                alert_level="none",
                closest_bus_id="",
                closest_distance_km=999.0,
                waypoint_index=0,
                progress_on_segment=0.0
            )
        
        self.add_event(f"✅ System initialized. All {self.NUM_BUSES} buses are idle at Tumkur.")
    
    def dispatch_bus(self):
        """Find an idle bus and set it to moving."""
        for bus in self.buses.values():
            if bus.status == BusStatus.IDLE:
                bus.status = BusStatus.MOVING
                bus.speed = self.BASE_SPEED
                self.add_event(f"🚌 {bus.name} dispatched from Tumkur, heading to Bangalore.")
                return # Dispatch only one bus at a time
    
    def add_event(self, message: str):
        """Log an event with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        event = f"[{timestamp}] {message}"
        self.event_log.append(event)
        if len(self.event_log) > self.max_log_size:
            self.event_log.pop(0)
    
    def get_state(self) -> dict:
        """Return the current simulation state as a serializable dict."""
        return {
            "buses": [
                {
                    "id": bus.id,
                    "name": bus.name,
                    "latitude": round(bus.latitude, 6),
                    "longitude": round(bus.longitude, 6),
                    "destination_lat": round(bus.destination_lat, 6),
                    "destination_lon": round(bus.destination_lon, 6),
                    "status": bus.status,
                    "speed": round(bus.speed, 1),
                    "heading": round(bus.heading, 1),
                    "alert_level": bus.alert_level,
                    "closest_bus_id": bus.closest_bus_id,
                    "closest_distance_km": round(bus.closest_distance_km, 2),
                    "alternative_routes": bus.alternative_routes,
                }
                for bus in self.buses.values()
            ],
            "event_log": self.event_log,
            "config": {
                "alert_warning_km": self.ALERT_WARNING,
                "alert_critical_km": self.ALERT_CRITICAL,
                "num_buses": self.NUM_BUSES,
            },
            "admin_mode": self.admin_mode_active,
        }


# ============================================================================
# SIMULATION TICK LOGIC
# ============================================================================

class BusSimulation:
    """Handles bus movement and proximity detection logic."""
    
    def __init__(self, state: SimulationState):
        self.state = state
    
    def tick(self):
        """Execute one simulation tick (1 second)."""
        current_time = asyncio.get_event_loop().time()

        # Initialize dispatch time on the first tick
        if self.state.last_dispatch_time is None:
            self.state.last_dispatch_time = current_time

        # Step 1: Dispatch new buses periodically
        if current_time - self.state.last_dispatch_time > self.state.dispatch_interval:
            self.state.dispatch_bus()
            self.state.last_dispatch_time = current_time

        # Step 2: Update bus positions
        self._update_positions()
        
        # Step 3: Check for arrivals at destination
        self._handle_arrivals()
        
        # Step 4: Calculate proximity alerts
        self._check_proximity_alerts()
    
    def _update_positions(self):
        """Update each bus position towards its destination."""
        for bus in self.state.buses.values():
            if bus.status != BusStatus.MOVING:
                continue

            current_loc = bus.current_location()
            destination_loc = bus.destination_location()
            distance_to_dest = current_loc.distance_to(destination_loc)

            # If bus is very close to its destination waypoint, mark for arrival
            if distance_to_dest < 0.1:  # Less than 100 meters
                bus.status = BusStatus.BOARDING
                # Snap to destination to avoid overshooting
                bus.latitude = bus.destination_lat
                bus.longitude = bus.destination_lon
                continue

            # Movement for this tick (in km)
            movement_km = (bus.speed / 3600) * self.state.TICK_INTERVAL
            
            # Interpolate position
            fraction_of_travel = movement_km / distance_to_dest
            
            bus.latitude += (bus.destination_lat - bus.latitude) * fraction_of_travel
            bus.longitude += (bus.destination_lon - bus.longitude) * fraction_of_travel

            # Calculate heading
            dlat = bus.destination_lat - bus.latitude
            dlon = bus.destination_lon - bus.longitude
            bus.heading = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360

    def _handle_arrivals(self):
        """Handle buses that have arrived at a waypoint and assign the next one."""
        final_destination = Location(12.9716, 77.5946)  # Bangalore endpoint
        
        for bus in self.state.buses.values():
            if bus.status == BusStatus.BOARDING:
                current_loc = bus.current_location()
                
                # Check if bus is very close to final destination
                if current_loc.distance_to(final_destination) < 0.5:  # Within 500m of Bangalore
                    self.state.add_event(f"✅ {bus.name} reached final destination in Bangalore!")
                    bus.status = BusStatus.IDLE
                    bus.speed = 0
                    bus.latitude = final_destination.latitude
                    bus.longitude = final_destination.longitude
                    bus.current_route = None
                    continue
                
                # If bus has a custom route, follow it
                if bus.current_route and len(bus.current_route) > 0:
                    bus.waypoint_index = (bus.waypoint_index + 1) % len(bus.current_route)
                    
                    # Check if reached end of custom route
                    if bus.waypoint_index == 0:
                        # Go to final destination
                        bus.destination_lat = final_destination.latitude
                        bus.destination_lon = final_destination.longitude
                        bus.current_route = None
                        bus.status = BusStatus.MOVING
                        self.state.add_event(f"📍 {bus.name} exiting divert route, heading to Bangalore")
                    else:
                        # Go to next waypoint on custom route
                        waypoint = bus.current_route[bus.waypoint_index]
                        bus.destination_lat = waypoint[0]
                        bus.destination_lon = waypoint[1]
                        bus.status = BusStatus.MOVING
                    continue
                
                # Follow normal highway route
                bus.waypoint_index = (bus.waypoint_index + 1) % len(self.state.route_waypoints)
                
                # If it's the last waypoint, head to final destination
                if bus.waypoint_index == 0:
                    self.state.add_event(f"🚌 {bus.name} reached end of route, heading to Bangalore.")
                    bus.destination_lat = final_destination.latitude
                    bus.destination_lon = final_destination.longitude
                    bus.status = BusStatus.MOVING
                    bus.speed = self.state.BASE_SPEED
                    continue
                
                # Set new destination
                dest_waypoint = self.state.route_waypoints[bus.waypoint_index]
                bus.destination_lat = dest_waypoint[0]
                bus.destination_lon = dest_waypoint[1]
                
                bus.status = BusStatus.MOVING
                bus.speed = self.state.BASE_SPEED
                
                self.state.add_event(f"📍 {bus.name} continuing to next waypoint.")
    
    def _check_proximity_alerts(self):
        """Check distance between all buses and trigger alerts."""
        bus_list = list(self.state.buses.values())
        
        for i, bus in enumerate(bus_list):
            min_distance = 999.0
            closest_bus_id = ""
            alert_level = "none"
            
            # Find closest bus
            for other_bus in bus_list:
                if other_bus.id != bus.id:
                    distance = bus.current_location().distance_to(other_bus.current_location())
                    
                    if distance < min_distance:
                        min_distance = distance
                        closest_bus_id = other_bus.id
            
            # Determine alert level
            if min_distance < self.state.ALERT_CRITICAL:
                alert_level = "critical"
            elif min_distance < self.state.ALERT_WARNING:
                alert_level = "warning"
            else:
                alert_level = "none"
            
            # Update bus state
            bus.closest_distance_km = min_distance
            bus.closest_bus_id = closest_bus_id
            
            # Only update if alert level changed
            if alert_level != bus.alert_level:
                bus.alert_level = alert_level
                
                if alert_level == "critical":
                    self.state.add_event(
                        f"🚨 CRITICAL: {bus.name} is {min_distance:.1f} km from {closest_bus_id}!"
                    )
                elif alert_level == "warning":
                    self.state.add_event(
                        f"⚠️ WARNING: {bus.name} is {min_distance:.1f} km from {closest_bus_id}"
                    )
    
    def slow_down_bus(self, bus_id: str):
        """Admin: Slow down a specific bus."""
        if bus_id in self.state.buses:
            bus = self.state.buses[bus_id]
            bus.speed = max(10, bus.speed * 0.7)  # Reduce by 30%, min 10 km/h
            self.state.add_event(f"🚦 {bus.name} slowed to {bus.speed:.1f} km/h")
    
    def speed_up_bus(self, bus_id: str):
        """Admin: Speed up a specific bus."""
        if bus_id in self.state.buses:
            bus = self.state.buses[bus_id]
            bus.speed = min(80, bus.speed * 1.3)  # Increase by 30%, max 80 km/h
            self.state.add_event(f"⚡ {bus.name} speeded to {bus.speed:.1f} km/h")
    
    def stop_bus(self, bus_id: str):
        """Admin: Stop a bus."""
        if bus_id in self.state.buses:
            bus = self.state.buses[bus_id]
            if bus.status != BusStatus.STOPPED:
                bus.status = BusStatus.STOPPED
                bus.speed = 0
                self.state.add_event(f"⏹️ {bus.name} stopped by admin")
    
    def resume_bus(self, bus_id: str):
        """Admin: Resume a stopped bus."""
        if bus_id in self.state.buses:
            bus = self.state.buses[bus_id]
            if bus.status == BusStatus.STOPPED:
                bus.status = BusStatus.MOVING
                bus.speed = self.state.BASE_SPEED
                self.state.add_event(f"▶️ {bus.name} resumed by admin")
    
    def divert_bus(self, bus_id: str):
        """Admin: Generate alternative routes for a bus to the same destination."""
        if bus_id in self.state.buses:
            bus = self.state.buses[bus_id]
            
            # Always clear old routes first
            bus.alternative_routes = None
            bus.current_route = None
            
            # Generate 3 alternative routes with different offset amounts
            current_loc = Location(bus.latitude, bus.longitude)
            destination_loc = Location(12.9716, 77.5946)  # Bangalore
            
            routes = []
            
            # Route 1: Slight left deviation
            route1 = self._generate_diverted_route(current_loc, destination_loc, offset=0.02, direction=1)
            routes.append(route1)
            
            # Route 2: Slight right deviation  
            route2 = self._generate_diverted_route(current_loc, destination_loc, offset=0.02, direction=-1)
            routes.append(route2)
            
            # Route 3: Large detour left
            route3 = self._generate_diverted_route(current_loc, destination_loc, offset=0.04, direction=1)
            routes.append(route3)
            
            # Store routes on the bus
            bus.alternative_routes = routes
            
            self.state.add_event(f"🔄 {bus.name}: Divert options generated. Select a route.")
    
    def _generate_diverted_route(self, start: Location, end: Location, offset: float, direction: int) -> list:
        """Generate a diverted route with waypoint deviations."""
        # Create intermediate points with offset
        route = [
            [start.latitude, start.longitude]
        ]
        
        # Number of segments for the detour
        segments = 3
        
        for i in range(1, segments + 1):
            # Interpolate position along the direct path
            t = i / (segments + 1)
            lat = start.latitude + (end.latitude - start.latitude) * t
            lon = start.longitude + (end.longitude - start.longitude) * t
            
            # Add offset perpendicular to the route
            offset_lat = offset * direction * (1 - abs(2*t - 1))  # Peak offset at midpoint
            offset_lon = offset * direction * 0.5 * (1 - abs(2*t - 1))
            
            route.append([lat + offset_lat, lon + offset_lon])
        
        # Add destination
        route.append([end.latitude, end.longitude])
        
        return route
    
    def select_route(self, bus_id: str, route_index: int):
        """Admin: Select an alternative route for the bus to follow."""
        if bus_id in self.state.buses:
            bus = self.state.buses[bus_id]
            
            if bus.alternative_routes and 0 <= route_index < len(bus.alternative_routes):
                selected_route = bus.alternative_routes[route_index]
                
                # Store the custom route
                bus.current_route = selected_route
                
                # Move bus to the start of the custom route
                start_waypoint = selected_route[0]
                bus.latitude = start_waypoint[0]
                bus.longitude = start_waypoint[1]
                bus.waypoint_index = 0
                
                # Set destination to first waypoint on the route
                if len(selected_route) > 1:
                    first_waypoint = selected_route[1]
                    bus.destination_lat = first_waypoint[0]
                    bus.destination_lon = first_waypoint[1]
                    bus.status = BusStatus.MOVING
                    bus.speed = self.state.BASE_SPEED
                    
                    self.state.add_event(f"🗺️ {bus.name} now following diverted route {route_index + 1}")
                
                # Clear alternative routes since one is selected
                bus.alternative_routes = None
    
    def reset_system(self):
        """Admin: Reset all buses to initial state."""
        self.state._initialize_buses()
        self.state.add_event("🔄 System reset - all buses reinitialized at start position")


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

# Global state and simulation
sim_state = SimulationState()
simulation = BusSimulation(sim_state)
active_connections: Set[WebSocket] = set()
simulation_running = False


async def simulation_loop():
    """
    Main simulation loop: ticks the simulation every TICK_INTERVAL seconds
    and broadcasts state to all connected WebSocket clients.
    """
    global simulation_running
    simulation_running = True
    try:
        while True:
            # Execute one simulation tick
            simulation.tick()
            
            # Broadcast state to all connected clients
            state_data = sim_state.get_state()
            state_json = json.dumps(state_data)
            
            # Send to all active WebSocket connections
            disconnected = set()
            for connection in active_connections:
                try:
                    await connection.send_text(state_json)
                except Exception as e:
                    print(f"Error sending to WebSocket: {e}")
                    disconnected.add(connection)
            
            # Clean up disconnected clients
            for conn in disconnected:
                active_connections.discard(conn)
            
            # Wait for next tick
            await asyncio.sleep(sim_state.TICK_INTERVAL)
    except asyncio.CancelledError:
        simulation_running = False
    except Exception as e:
        print(f"Simulation loop error: {e}")
        simulation_running = False


simulation_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager: starts simulation on startup, cancels on shutdown.
    """
    global simulation_task
    # Startup
    simulation_task = asyncio.create_task(simulation_loop())
    yield
    # Shutdown
    if simulation_task:
        simulation_task.cancel()
        try:
            await simulation_task
        except asyncio.CancelledError:
            pass


# Create FastAPI app with CORS and lifespan
app = FastAPI(title="Bus Tracking & Alert System - Tumkur to Bangalore", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    await websocket.accept()
    active_connections.add(websocket)
    
    sim_state.add_event(f"🟢 Client connected")
    
    try:
        await websocket.send_text(json.dumps(sim_state.get_state()))
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            cmd_type = message.get("type")
            
            if cmd_type == "slow_down":
                bus_id = message.get("bus_id")
                simulation.slow_down_bus(bus_id)
            
            elif cmd_type == "speed_up":
                bus_id = message.get("bus_id")
                simulation.speed_up_bus(bus_id)
            
            elif cmd_type == "stop":
                bus_id = message.get("bus_id")
                simulation.stop_bus(bus_id)
            
            elif cmd_type == "resume":
                bus_id = message.get("bus_id")
                simulation.resume_bus(bus_id)
            
            elif cmd_type == "divert":
                bus_id = message.get("bus_id")
                simulation.divert_bus(bus_id)
            
            elif cmd_type == "select_route":
                bus_id = message.get("bus_id")
                route_index = message.get("route_index")
                simulation.select_route(bus_id, route_index)
            
            elif cmd_type == "reset":
                simulation.reset_system()
            
            elif cmd_type == "toggle_admin":
                sim_state.admin_mode_active = not sim_state.admin_mode_active
                status = "enabled" if sim_state.admin_mode_active else "disabled"
                sim_state.add_event(f"👨‍💼 Admin mode {status}")
    
    except WebSocketDisconnect:
        active_connections.discard(websocket)
        sim_state.add_event(f"🔴 Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        active_connections.discard(websocket)


# ============================================================================
# REST ENDPOINTS
# ============================================================================

@app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "Bus Tracking - Tumkur to Bangalore"}

@app.get("/state")
def get_state():
    """Get current simulation state."""
    return sim_state.get_state()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
