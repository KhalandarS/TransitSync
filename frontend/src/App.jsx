import React, { useEffect, useState, useRef, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

/**
 * Bus Tracking & Alert System - React Frontend
 * Tumkur to Bangalore highway route tracking with proximity alerts
 * Uses Stadia Maps for road visibility in India
 */

// Route waypoints from Tumkur to Bangalore (NH48 Highway)
const HIGHWAY_WAYPOINTS = [
  [13.3426, 77.1023], // Tumkur (start)
  [13.3300, 77.1200],
  [13.3150, 77.1450],
  [13.2980, 77.1700],
  [13.2800, 77.1950],
  [13.2600, 77.2200],
  [13.2350, 77.2450],
  [13.2100, 77.2700],
  [13.1850, 77.2950],
  [13.1600, 77.3200],
  [13.1350, 77.3450],
  [13.1100, 77.3700],
  [13.0900, 77.3950],
  [13.0700, 77.4200],
  [13.0500, 77.4450],
  [13.0300, 77.4700],
  [13.0100, 77.4950],
  [12.9950, 77.5200],
  [12.9800, 77.5450],
  [12.9716, 77.5946], // Bangalore (end)
];

const BusTrackingApp = () => {
  const [buses, setBuses] = useState([]);
  const [eventLog, setEventLog] = useState([]);
  const [config, setConfig] = useState({
    alert_critical_km: 5,
    alert_warning_km: 10
  });
  const [connected, setConnected] = useState(false);
  const [adminMode, setAdminMode] = useState(false);
  const [selectedBus, setSelectedBus] = useState(null);
  const [divertBusId, setDivertBusId] = useState(null);  // Bus with divert options
  const [divertRoutes, setDivertRoutes] = useState([]);  // Alternative routes for divert

  const wsRef = useRef(null);
  const mapRef = useRef(null);
  const busMarkersRef = useRef({});
  const routePolylinesRef = useRef({});  // Store route polylines
  const logEndRef = useRef(null);

  // =========================================================================
  // WEBSOCKET CONNECTION
  // =========================================================================

  const connectWebSocket = useCallback(() => {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.hostname}:8000/ws`;
      
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('🟢 WebSocket connected');
        setConnected(true);
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        setBuses(data.buses || []);
        setEventLog(data.event_log || []);
        setConfig(data.config || { alert_critical_km: 5, alert_warning_km: 10 });
        setAdminMode(data.admin_mode || false);

        // Check if any bus has alternative routes (divert options)
        const busWithRoutes = data.buses?.find(b => b.alternative_routes && b.alternative_routes.length > 0);
        if (busWithRoutes) {
          setDivertBusId(busWithRoutes.id);
          setDivertRoutes(busWithRoutes.alternative_routes);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnected(false);
      };

      ws.onclose = () => {
        console.log('🔴 WebSocket disconnected');
        setConnected(false);
        setTimeout(connectWebSocket, 3000);
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
      setTimeout(connectWebSocket, 3000);
    }
  }, []);

  // =========================================================================
  // SEND COMMAND TO BACKEND
  // =========================================================================

  const sendCommand = (command) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(command));
    }
  };

  // =========================================================================
  // ADMIN CONTROLS
  // =========================================================================

  const slowDown = (busId) => {
    sendCommand({ type: 'slow_down', bus_id: busId });
  };

  const speedUp = (busId) => {
    sendCommand({ type: 'speed_up', bus_id: busId });
  };

  const stopBus = (busId) => {
    sendCommand({ type: 'stop', bus_id: busId });
  };

  const resumeBus = (busId) => {
    sendCommand({ type: 'resume', bus_id: busId });
  };

  const divertBus = (busId) => {
    // Always generate fresh routes when divert is clicked
    sendCommand({ type: 'divert', bus_id: busId });
  };

  const selectDivertRoute = (routeIndex) => {
    if (divertBusId) {
      sendCommand({ type: 'select_route', bus_id: divertBusId, route_index: routeIndex });
      setDivertBusId(null);
      setDivertRoutes([]);
      // Clear route polylines from map
      Object.values(routePolylinesRef.current).forEach(polyline => {
        if (mapRef.current) mapRef.current.removeLayer(polyline);
      });
      routePolylinesRef.current = {};
    }
  };

  const resetSystem = () => {
    sendCommand({ type: 'reset' });
  };

  const toggleAdminMode = () => {
    sendCommand({ type: 'toggle_admin' });
  };

  // =========================================================================
  // MAP INITIALIZATION & UPDATES
  // =========================================================================

  useEffect(() => {
    if (!mapRef.current) {
      // Center on Bangalore/Tumkur region in India
      const defaultCenter = [13.15, 77.35];
      const map = L.map('map').setView(defaultCenter, 10);

      L.tileLayer('https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}.png', {
        attribution: '&copy; Stadia Maps, &copy; OpenStreetMap',
        maxZoom: 18,
        minZoom: 5,
      }).addTo(map);

      // Draw the route as a blue polyline
      L.polyline(HIGHWAY_WAYPOINTS, {
        color: 'blue',
        weight: 3,
        opacity: 0.7,
        dashArray: '5, 5',
        lineJoin: 'round'
      }).addTo(map);

      // Add markers for start and end points
      L.circleMarker([13.3426, 77.1023], {
        radius: 10,
        fillColor: 'green',
        color: '#000',
        weight: 2,
        opacity: 1,
        fillOpacity: 0.9
      }).bindPopup('📍 Tumkur (Start)').addTo(map);

      L.circleMarker([12.9716, 77.5946], {
        radius: 10,
        fillColor: 'red',
        color: '#000',
        weight: 2,
        opacity: 1,
        fillOpacity: 0.9
      }).bindPopup('📍 Bangalore (End)').addTo(map);

      mapRef.current = map;
    }
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;

    // Clear existing route polylines
    Object.values(routePolylinesRef.current).forEach(polyline => {
      if (mapRef.current) mapRef.current.removeLayer(polyline);
    });
    routePolylinesRef.current = {};

    // Draw alternative routes for buses with divert options
    buses.forEach((bus) => {
      if (bus.alternative_routes && bus.alternative_routes.length > 0) {
        bus.alternative_routes.forEach((route, routeIdx) => {
          const polylineKey = `${bus.id}-route-${routeIdx}`;
          const polyline = L.polyline(route, {
            color: '#00FFFF',  // Cyan for alternative routes
            weight: 2,
            opacity: 0.6,
            dashArray: '5, 5',
            lineJoin: 'round'
          }).addTo(mapRef.current);
          
          routePolylinesRef.current[polylineKey] = polyline;
        });
      }
    });

    buses.forEach((bus) => {
      const markerId = bus.id;
      const latLng = L.latLng(bus.latitude, bus.longitude);

      if (busMarkersRef.current[markerId]) {
        busMarkersRef.current[markerId].setLatLng(latLng);
      } else {
        // Determine color based on status and speed
        let color = 'blue';
        if (bus.status === 'stopped') {
          color = '#FF6B6B'; // Red for stopped
        } else if (bus.status === 'idle') {
          color = '#808080'; // Gray for idle
        } else if (bus.alert_level === 'critical') {
          color = '#FF0000'; // Bright red for critical proximity
        } else if (bus.alert_level === 'warning') {
          color = '#FFA500'; // Orange for warning proximity
        } else if (bus.speed < 50) {
          color = '#FFD700'; // Yellow for slow moving
        } else if (bus.speed > 150) {
          color = '#00FF00'; // Green for fast moving
        } else {
          color = '#1E90FF'; // Blue for normal moving
        }
        
        const marker = L.circleMarker(latLng, {
          radius: 8,
          fillColor: color,
          color: '#000',
          weight: 2,
          opacity: 1,
          fillOpacity: 0.8,
        })
          .bindPopup(`<b>${bus.name}</b><br/>Speed: ${bus.speed.toFixed(1)} km/h<br/>Status: ${bus.status}`)
          .addTo(mapRef.current);

        busMarkersRef.current[markerId] = marker;
      }

      // Update color based on current status and speed
      let color = 'blue';
      if (bus.status === 'stopped') {
        color = '#FF6B6B'; // Red for stopped
      } else if (bus.status === 'idle') {
        color = '#808080'; // Gray for idle
      } else if (bus.alert_level === 'critical') {
        color = '#FF0000'; // Bright red for critical proximity
      } else if (bus.alert_level === 'warning') {
        color = '#FFA500'; // Orange for warning proximity
      } else if (bus.speed < 50) {
        color = '#FFD700'; // Yellow for slow moving
      } else if (bus.speed > 150) {
        color = '#00FF00'; // Green for fast moving
      } else {
        color = '#1E90FF'; // Blue for normal moving
      }
      busMarkersRef.current[markerId].setStyle({ fillColor: color });
    });

    Object.keys(busMarkersRef.current).forEach((markerId) => {
      if (!buses.find((bus) => bus.id === markerId)) {
        mapRef.current.removeLayer(busMarkersRef.current[markerId]);
        delete busMarkersRef.current[markerId];
      }
    });
  }, [buses]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [eventLog]);

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connectWebSocket]);

  // =========================================================================
  // RENDER
  // =========================================================================

  return (
    <div className="w-full h-screen bg-gray-900 text-white flex flex-col">
      {/* HEADER */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-800 p-4 shadow-lg">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">🚌 Bus Tracking System</h1>
            <p className="text-blue-100 text-sm">Real-time monitoring with proximity alerts</p>
          </div>
          <div className="flex gap-2 items-center">
            <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
              connected ? 'bg-green-500' : 'bg-red-500'
            }`}>
              {connected ? '🟢 Connected' : '🔴 Disconnected'}
            </span>
            <button
              onClick={toggleAdminMode}
              className={`px-4 py-2 rounded-lg font-semibold transition ${
                adminMode
                  ? 'bg-red-600 hover:bg-red-700'
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              👨‍💼 Admin {adminMode ? 'ON' : 'OFF'}
            </button>
          </div>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div className="flex-1 flex gap-4 overflow-hidden p-4">
        {/* MAP */}
        <div className="flex-1 rounded-lg overflow-hidden shadow-lg border-2 border-blue-600">
          <div id="map" className="w-full h-full"></div>
        </div>

        {/* SIDEBAR */}
        <div className="w-96 flex flex-col gap-4 overflow-hidden">
          {/* BUSES PANEL */}
          <div className="bg-gray-800 rounded-lg shadow-lg flex-1 overflow-hidden flex flex-col border-l-4 border-blue-600">
            <div className="bg-gray-700 p-3 font-bold text-lg">
              🚍 Buses ({buses.length})
            </div>
            <div className="overflow-y-auto flex-1 p-3 space-y-2">
              {buses.map((bus) => (
                <div
                  key={bus.id}
                  onClick={() => setSelectedBus(selectedBus === bus.id ? null : bus.id)}
                  className={`p-3 rounded-lg cursor-pointer transition border-2 ${
                    selectedBus === bus.id
                      ? 'border-yellow-400 bg-gray-700'
                      : 'border-gray-600 bg-gray-750 hover:bg-gray-700'
                  } ${
                    bus.alert_level === 'critical'
                      ? 'border-red-500 bg-red-900'
                      : bus.alert_level === 'warning'
                      ? 'border-orange-500 bg-orange-900'
                      : ''
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="font-bold">{bus.name}</span>
                    <span className="text-xs bg-gray-600 px-2 py-1 rounded">
                      {bus.status}
                    </span>
                  </div>
                  <div className="text-xs text-gray-300 space-y-1">
                    <div>Speed: {bus.speed.toFixed(1)} km/h</div>
                    <div>Heading: {bus.heading.toFixed(0)}°</div>
                    <div>Closest: {bus.closest_bus_id} ({bus.closest_distance_km.toFixed(1)} km)</div>
                  </div>

              {adminMode && selectedBus === bus.id && (
                <div className="mt-3 pt-3 border-t border-gray-600">
                  <div className="grid grid-cols-2 gap-2 mb-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        slowDown(bus.id);
                      }}
                      className="bg-orange-600 hover:bg-orange-700 px-2 py-2 rounded text-xs font-semibold transition"
                    >
                      🚦 Slow Down
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        speedUp(bus.id);
                      }}
                      className="bg-green-600 hover:bg-green-700 px-2 py-2 rounded text-xs font-semibold transition"
                    >
                      ⚡ Speed Up
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        bus.status === 'stopped' ? resumeBus(bus.id) : stopBus(bus.id);
                      }}
                      className={`${
                        bus.status === 'stopped'
                          ? 'bg-green-600 hover:bg-green-700'
                          : 'bg-red-600 hover:bg-red-700'
                      } px-2 py-2 rounded text-xs font-semibold transition`}
                    >
                      {bus.status === 'stopped' ? '▶️ Resume' : '⏹️ Stop'}
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        divertBus(bus.id);
                      }}
                      className="bg-purple-600 hover:bg-purple-700 px-2 py-2 rounded text-xs font-semibold transition"
                    >
                      🔄 Divert
                    </button>
                  </div>
                </div>
              )}
                </div>
              ))}
            </div>
          </div>

          {/* ALERT THRESHOLDS */}
          <div className="bg-gray-800 rounded-lg shadow-lg p-3 border-l-4 border-yellow-600">
            <div className="font-bold text-sm mb-2">⚠️ Alert Thresholds</div>
            <div className="text-xs space-y-1 text-gray-300">
              <div>🔴 Critical: &lt; {config.alert_critical_km} km</div>
              <div>🟠 Warning: {config.alert_critical_km} - {config.alert_warning_km} km</div>
              <div>🟢 Safe: &gt; {config.alert_warning_km} km</div>
            </div>
          </div>

          {adminMode && (
            <button
              onClick={resetSystem}
              className="bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg font-semibold transition shadow-lg"
            >
              🔄 Reset System
            </button>
          )}
        </div>
      </div>

      {/* EVENT LOG FOOTER */}
      <div className="bg-gray-800 border-t-2 border-blue-600 h-32 overflow-y-auto p-3 font-mono text-xs">
        <div className="space-y-1">
          {eventLog.map((event, idx) => (
            <div key={idx} className="text-gray-300">
              {event}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </div>

      {/* DIVERT ROUTE SELECTION MODAL */}
      {divertBusId && divertRoutes.length > 0 && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 border-2 border-cyan-500 max-w-md shadow-2xl">
            <h2 className="text-2xl font-bold text-cyan-400 mb-4">
              🗺️ Select Alternate Route
            </h2>
            <p className="text-gray-300 mb-4">
              Choose one of {divertRoutes.length} available routes for the bus
            </p>
            <div className="space-y-3 mb-6">
              {divertRoutes.map((route, idx) => (
                <button
                  key={idx}
                  onClick={() => selectDivertRoute(idx)}
                  className="w-full bg-cyan-600 hover:bg-cyan-700 text-white font-bold py-3 px-4 rounded-lg transition border-2 border-cyan-500 hover:border-cyan-300"
                >
                  Route {idx + 1} ({route.length} waypoints)
                </button>
              ))}
            </div>
            <button
              onClick={() => {
                setDivertBusId(null);
                setDivertRoutes([]);
                Object.values(routePolylinesRef.current).forEach(polyline => {
                  if (mapRef.current) mapRef.current.removeLayer(polyline);
                });
                routePolylinesRef.current = {};
              }}
              className="w-full bg-gray-700 hover:bg-gray-600 text-gray-300 font-semibold py-2 px-4 rounded-lg transition"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default BusTrackingApp;
