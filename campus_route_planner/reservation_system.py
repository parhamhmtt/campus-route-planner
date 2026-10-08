import heapq


def _key(u1, u2):
    return tuple(sorted((u1, u2)))


class ReservationSystem:
    """Seat reservations per route, kept in a priority queue (lower number = higher priority)."""

    def __init__(self):
        self.routes = {}

    def set_capacity(self, u1, u2, capacity):
        if capacity < 0:
            raise ValueError("Capacity cannot be negative.")
        route = self.routes.setdefault(_key(u1, u2), {"capacity": 0, "queue": []})
        route["capacity"] = capacity

    def reserve(self, u1, u2, student_name, priority):
        route = self.routes.get(_key(u1, u2))
        if route is None:
            return False, "No capacity has been set for this route."
        if any(name == student_name for _, name in route["queue"]):
            return False, f"{student_name} already has a seat on this route."
        if len(route["queue"]) >= route["capacity"]:
            return False, "Route is full."
        heapq.heappush(route["queue"], (priority, student_name))
        return True, "Reservation confirmed."

    def view_reservations(self, u1, u2):
        route = self.routes.get(_key(u1, u2))
        return sorted(route["queue"]) if route else []
