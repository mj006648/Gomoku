

# **Project: Socket Programming - Gomoku **

## **1. Overview**

This project is a real-time multiplayer Gomoku game developed using Python's standard libraries. It is based on a client-server architecture, allowing multiple users to connect, play or spectate games, and interact through a real-time chat system. It reliably handles multiple connections using multithreading and implements all core requirements as well as advanced features for extra credit.

## **2. Features Implemented**

### **Core Features**

-   **Game Rooms**: Users can view a list of game rooms, create new rooms, or join existing ones. Each room supports exactly two players.
-   **Real-time Two-Player Gameplay**: Two players, assigned black and white stones, take turns playing on a standard 15x15 board.
-   **Spectator Mode**: Users can join an ongoing game as a spectator to watch the match in real-time.
-   **Server-side Game Mechanics**: The server validates all moves, enforces turn order, and automatically determines the winner when five stones are placed in a row.
-   **Real-time Interaction**: All player moves are instantly reflected on the screens of the opponent and all spectators.
-   **Server Architecture**: The server uses multithreading with `threading.RLock` to prevent deadlocks and ensure stable concurrent processing of multiple client connections.

### **Advanced Features**

-   **Spectator Chat Mode**:
    -   **Description**: Spectators can participate in the chat alongside players.
    -   **How to Test**: Log in as a spectator and send a chat message. The message will appear on all clients' screens, prefixed with `[Spectator]` and colored gray to distinguish it from player messages.

-   **Move Timer per Player**:
    -   **Description**: Each player has a 30-second time limit for their turn. Exceeding the time limit results in an automatic loss.
    -   **How to Test**: When it is your turn, a countdown timer will appear on the screen. Wait for 30 seconds without making a move. A game-over popup will appear, declaring you have lost by timeout.

-   **Reconnection Support**:
    -   **Description**: If a player's client disconnects unexpectedly, they are given a 60-second grace period to rejoin the game.
    -   **How to Test**: While in a game, force-close the client window or terminal. The opponent's client will show a disconnection message. Relaunch the client and log in with the *exact same nickname* within 60 seconds. You will be placed directly back into the ongoing game, not the lobby.

## **3. Technologies Used**

-   **Language**: Python 3
-   **Networking**: `socket`, `threading` (Python Standard Library)
-   **GUI**: `tkinter` (Python Standard Library)
-   **Data Format**: JSON

## **4. How to Run**

### **Prerequisites**

-   Python 3 must be installed.

### **Execution Steps**

1.  **Run the Server**: Navigate to the project directory in a terminal and execute:
    ```
    python3 server.py
    ```

2.  **Run Clients**: Open a new terminal for each client and execute:
    ```
    python3 client.py
    ```

3.  **How to Play**:
    -   **Connect**: Enter a unique nickname in each client window and click `Connect`.
    -   **Create/Join**: Use `Create Room` to make a new room, or `Refresh List` and `Join Room` to enter an existing one.
    -   **Spectate**: Select a game in progress and click `Spectate Room`.
    -   **Game End**: After the game concludes, a result is shown, and all clients automatically return to the lobby after 2 seconds.

## **5. Socket Communication Protocol Specification**

Communication between the client and server is handled using JSON-formatted messages, where each message is terminated by a newline character (`\n`).

### **Client → Server (C2S)**

| Message Type | Payload Example | Description |
| :--- | :--- | :--- |
| `login` | `{'nickname': 'p1'}` | Logs into the server with a nickname. |
| `list_rooms` | `{}` | Requests the list of game rooms. |
| `create_room` | `{'room_name': 'r1'}` | Creates a new game room. |
| `join_room` | `{'room_name': 'r1'}` | Joins a room as a player. |
| `spectate_room` | `{'room_name': 'r1'}` | Joins a room as a spectator. |
| `place_stone` | `{'row': 7, 'col': 7}` | Places a stone at given coordinates. |
| `chat_message` | `{'message': 'hi'}` | Sends a chat message. |

### **Server → Client (S2C)**

| Message Type | Payload Example | Description |
| :--- | :--- | :--- |
| `login_success` | `{}` | Notifies of a successful login. |
| `login_fail` | `{'reason': 'exist'}` | Notifies of a failed login with a reason. |
| `reconnect_success`| `{'room_name': 'r1', ...}` | Confirms successful reconnection and sends game state. |
| `room_list` | `{'rooms': [..]}` | Sends the list of game rooms. |
| `join_success` | `{'room_name': 'r1', 'color': 'black'}` | Confirms room entry and assigns a stone color. |
| `spectate_success`| `{'room_name': 'r1', ...}` | Confirms spectator entry and sends game state. |
| `game_start` | `{'opponent': 'p2', ...}` | Notifies that the game has started. |
| `update_board` | `{'row': 7, 'col': 7, 'color': 'black'}` | Broadcasts the position of a newly placed stone. |
| `update_turn` | `{'turn': 'white', 'time_limit': 30}` | Broadcasts the current turn and remaining time. |
| `chat_update` | `{'sender': 'p1', 'message': 'hi', 'is_spectator': false}`| Broadcasts a new chat message. |
| `game_over` | `{'winner': 'black', 'reason': 'win'}`| Announces the end of the game with a winner/reason. |
| `opponent_disconnected`| `{'nickname': 'p2'}` | Notifies that the opponent has disconnected. |
| `opponent_reconnected`| `{'nickname': 'p2'}` | Notifies that the opponent has reconnected. |
| `error` | `{'message': 'Room is full.'}` | Sends a generic error message. |
