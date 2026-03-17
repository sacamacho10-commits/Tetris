from flask import Flask, jsonify, request, send_from_directory
import random
import threading
import time

app = Flask(__name__, static_folder='static', static_url_path='')

WIDTH = 10
HEIGHT = 20
DROP_INTERVAL = 0.5

SHAPES = {
    'I': [
        [(0,1),(1,1),(2,1),(3,1)],
        [(2,0),(2,1),(2,2),(2,3)],
    ],
    'O': [
        [(1,0),(2,0),(1,1),(2,1)],
    ],
    'T': [
        [(1,0),(0,1),(1,1),(2,1)],
        [(1,0),(1,1),(2,1),(1,2)],
        [(0,1),(1,1),(2,1),(1,2)],
        [(1,0),(0,1),(1,1),(1,2)],
    ],
    'L': [
        [(0,0),(0,1),(1,1),(2,1)],
        [(1,0),(2,0),(1,1),(1,2)],
        [(0,1),(1,1),(2,1),(2,2)],
        [(1,0),(1,1),(1,2),(0,2)],
    ],
    'J': [
        [(2,0),(0,1),(1,1),(2,1)],
        [(1,0),(1,1),(1,2),(2,2)],
        [(0,1),(1,1),(2,1),(0,2)],
        [(0,0),(1,0),(1,1),(1,2)],
    ],
    'S': [
        [(1,0),(2,0),(0,1),(1,1)],
        [(1,0),(1,1),(2,1),(2,2)],
    ],
    'Z': [
        [(0,0),(1,0),(1,1),(2,1)],
        [(2,0),(1,1),(2,1),(1,2)],
    ],
}

board = [[0] * WIDTH for _ in range(HEIGHT)]
current_piece = None
next_piece = None
lock = threading.Lock()
score = 0
level = 1
is_running = False
game_over = False
leaderboard = []


def new_piece():
    shape = random.choice(list(SHAPES.keys()))
    return {
        'shape': shape,
        'rotation': 0,
        'x': (WIDTH - 4) // 2,
        'y': 0,
    }


def piece_cells(piece):
    shape = piece['shape']
    rotation = piece['rotation'] % len(SHAPES[shape])
    pattern = SHAPES[shape][rotation]
    return [(piece['x'] + px, piece['y'] + py) for px, py in pattern]


def valid_position(piece, x=None, y=None, rotation=None):
    x = piece['x'] if x is None else x
    y = piece['y'] if y is None else y
    rotation = piece['rotation'] if rotation is None else rotation

    shape = piece['shape']
    pat = SHAPES[shape][rotation % len(SHAPES[shape])]

    for px, py in pat:
        bx = x + px
        by = y + py
        if bx < 0 or bx >= WIDTH or by < 0 or by >= HEIGHT:
            return False
        if board[by][bx] != 0:
            return False
    return True


def lock_piece():
    global current_piece, next_piece, score
    if current_piece is None:
        return

    for x, y in piece_cells(current_piece):
        if 0 <= y < HEIGHT and 0 <= x < WIDTH:
            board[y][x] = 1

    new_board = [row for row in board if any(cell == 0 for cell in row)]
    cleared = HEIGHT - len(new_board)
    if cleared > 0:
        for _ in range(cleared):
            new_board.insert(0, [0] * WIDTH)
        for r in range(HEIGHT):
            board[r] = new_board[r]

    score += 100 * cleared
    current_piece = next_piece
    next_piece = new_piece()

    if current_piece is None or not valid_position(current_piece):
        global is_running, game_over
        is_running = False
        game_over = True
        current_piece = None
        return


def add_to_leaderboard(name, value):
    global leaderboard
    leaderboard.append({'name': name[:16], 'score': value})
    leaderboard = sorted(leaderboard, key=lambda e: e['score'], reverse=True)[:10]


def reset_game():
    global board, current_piece, next_piece, score, level, is_running, game_over
    board = [[0] * WIDTH for _ in range(HEIGHT)]
    current_piece = new_piece()
    next_piece = new_piece()
    score = 0
    level = 1
    is_running = True
    game_over = False


def step_down():
    global current_piece
    trial = current_piece.copy()
    trial['y'] += 1
    if valid_position(trial):
        current_piece = trial
    else:
        lock_piece()


def apply_action(action):
    global current_piece
    if action == 'left':
        trial = current_piece.copy(); trial['x'] -= 1
        if valid_position(trial):
            current_piece = trial
    elif action == 'right':
        trial = current_piece.copy(); trial['x'] += 1
        if valid_position(trial):
            current_piece = trial
    elif action == 'rotate':
        trial = current_piece.copy(); trial['rotation'] += 1
        if valid_position(trial):
            current_piece = trial
    elif action == 'down':
        step_down()


def game_loop():
    while True:
        time.sleep(DROP_INTERVAL)
        with lock:
            if not is_running:
                continue
            if current_piece is None:
                continue
            step_down()


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/state')
def state():
    with lock:
        display = [row.copy() for row in board]
        if current_piece:
            for x, y in piece_cells(current_piece):
                if 0 <= y < HEIGHT and 0 <= x < WIDTH:
                    display[y][x] = 2

        return jsonify({
            'width': WIDTH,
            'height': HEIGHT,
            'board': display,
            'score': score,
            'level': level,
            'is_running': is_running,
            'game_over': game_over,
            'leaderboard': leaderboard,
            'next_piece': next_piece,
        })


@app.route('/action', methods=['POST'])
def action():
    payload = request.get_json(silent=True) or {}
    act = payload.get('action')
    username = payload.get('name', 'Anonymous')
    with lock:
        if act == 'start' or act == 'reset':
            reset_game()
            return jsonify({'ok': True})

        if act == 'submit_score' and game_over:
            add_to_leaderboard(username, score)
            return jsonify({'ok': True})

        if act in ['left', 'right', 'rotate', 'down']:
            if not is_running or game_over:
                return jsonify({'ok': False}), 400
            apply_action(act)
            return jsonify({'ok': True})

    return jsonify({'ok': False}), 400


@app.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    with lock:
        return jsonify({'leaderboard': leaderboard})


if __name__ == '__main__':
    with lock:
        reset_game()
    t = threading.Thread(target=game_loop, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=5001, debug=True)
