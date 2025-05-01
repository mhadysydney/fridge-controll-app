<?php
// Configure logging
header('Content-Type: application/json');
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('X-XSS-Protection: 1; mode=block');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    header('Access-Control-Allow-Origin: *');
    header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
    header('Access-Control-Allow-Headers: Content-Type, Authorization');
    exit;
}
header('Access-Control-Allow-Origin: *');
$log_file = 'api_server.log'; // Replace 'username' with your cPanel username
function log_message($level, $message) {
    global $log_file;
    $timestamp = date('Y-m-d H:i:s');
    $log_entry = "[$timestamp] $level: $message\n";
    file_put_contents($log_file, $log_entry, FILE_APPEND);
    // Also output to stderr for cPanel error logs
    error_log($log_entry);
}

// Initialize logging
try {
    if (!file_exists($log_file)) {
        file_put_contents($log_file, '');
        chmod($log_file, 0666);
    }
    log_message('INFO', 'Logging initialized successfully');
} catch (Exception $e) {
    error_log('Failed to initialize logging: ' . $e->getMessage());
}

// SQLite database
$db_file = 'grok_fmb_data_v6.db'; // Replace 'username' with your cPanel username
try {
    // Create database and tables if they don't exist
    $db = new SQLite3($db_file);
    $db->exec('CREATE TABLE IF NOT EXISTS gps_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        imei TEXT,
        timestamp TEXT,
        latitude REAL,
        longitude REAL,
        altitude INTEGER,
        speed REAL,
        angle REAL,
        satellites INTEGER,
        priority INTEGER
    )');
    $db->exec('CREATE TABLE IF NOT EXISTS io_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        imei TEXT,
        timestamp TEXT,
        io_id INTEGER,
        io_value INTEGER
    )');
    $db->exec('CREATE TABLE IF NOT EXISTS dout1_state (
        imei TEXT PRIMARY KEY,
        last_dout1_zero_time TEXT,
        dout1_active INTEGER,
        deactivate_time TEXT
    )');
    $db->exec('CREATE TABLE IF NOT EXISTS command_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        imei TEXT,
        command TEXT,
        created_at TEXT,
        sent INTEGER DEFAULT 0
    )');
    chmod($db_file, 0666);
    log_message('INFO', "Database initialized successfully at $db_file");
} catch (Exception $e) {
    log_message('ERROR', 'Database initialization failed: ' . $e->getMessage());
    http_response_code(500);
    echo json_encode(['error' => 'Server error']);
    exit;
}

// Handle API requests
$request_method = $_SERVER['REQUEST_METHOD'];
$request_uri = $_SERVER['REQUEST_URI'];
$path = parse_url($request_uri, PHP_URL_PATH);
$path_parts = explode('/', trim($path, '/'));

// Route requests
if(count($path_parts) >= 1 && $path_parts[0] === 'test' && $request_method === 'GET')
    echo json_encode(['message' => 'Welcome to the api server']);
elseif (count($path_parts) >= 2 && $path_parts[0] === 'dout1_status' && $request_method === 'GET') {
    $imei = $path_parts[1];
    try {
        $stmt = $db->prepare('SELECT dout1_active, deactivate_time FROM dout1_state WHERE imei = :imei');
        $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
        $result = $stmt->execute();
        $row = $result->fetchArray(SQLITE3_ASSOC);
        if ($row) {
            echo json_encode([
                'imei' => $imei,
                'dout1_active' => (bool)$row['dout1_active'],
                'deactivate_time' => $row['deactivate_time']
            ]);
        } else {
            http_response_code(200);
            echo json_encode(['dout1_active' => false,'deactivate_time'=>'2025-05-01 16:00:00']);
        }
    } catch (Exception $e) {
        log_message('ERROR', "Error in dout1_status for IMEI $imei: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(['error' => 'Server error']);
    }
} elseif (count($path_parts) >= 2 && $path_parts[0] === 'dout1_control' && $request_method === 'POST') {
    $imei = $path_parts[1];
    try {
        $input = json_decode(file_get_contents('php://input'), true);
        $activate = isset($input['activate']) ? (bool)$input['activate'] : null;
        if ($activate === null) {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid input']);
            exit;
        }
        $stmt = $db->prepare('SELECT dout1_active FROM dout1_state WHERE imei = :imei');
        $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
        $result = $stmt->execute();
        $row = $result->fetchArray(SQLITE3_ASSOC);
        if ($row) {
            $command = $activate ? 'setdigout 1 4000' : 'setdigout 0';
            $created_at = date('Y-m-d H:i:s');
            $stmt = $db->prepare('INSERT INTO command_queue (imei, command, created_at, sent) VALUES (:imei, :command, :created_at, 0)');
            $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
            $stmt->bindValue(':command', $command, SQLITE3_TEXT);
            $stmt->bindValue(':created_at', $created_at, SQLITE3_TEXT);
            $stmt->execute();
            log_message('INFO', "Manual command queued for IMEI $imei: $command");
            echo json_encode(['command' => $command, 'status' => 'queued']);
        } else {
            http_response_code(404);
            echo json_encode(['error' => 'IMEI not found']);
        }
    } catch (Exception $e) {
        log_message('ERROR', "Error in dout1_control for IMEI $imei: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(['error' => 'Server error']);
    }
} else {
    http_response_code(404);
    echo json_encode(['error:'=>'Path not found']);
}

$db->close();
?>