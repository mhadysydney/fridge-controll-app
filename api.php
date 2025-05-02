<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST');
header('Access-Control-Allow-Headers: Content-Type');

$dbPath = '/home/yourusername/fmb_data.db';
$logFile = '/home/yourusername/fmb_server.log';

// Initialize SQLite database
try {
    $db = new SQLite3($dbPath);
    $db->exec('CREATE TABLE IF NOT EXISTS gps_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        imei TEXT,
        timestamp TEXT,
        latitude REAL,
        longitude REAL,
        altitude INTEGER,
        speed INTEGER,
        angle INTEGER,
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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        imei TEXT UNIQUE,
        dout1_active INTEGER,
        deactivate_time TEXT
    )');
    $db->exec('CREATE TABLE IF NOT EXISTS command_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        imei TEXT,
        command TEXT,
        status TEXT,
        created_at TEXT
    )');
} catch (Exception $e) {
    file_put_contents($logFile, date('Y-m-d H:i:s') . ': Database init failed: ' . $e->getMessage() . "\n", FILE_APPEND);
    http_response_code(500);
    echo json_encode(['error' => 'Database error']);
    exit;
}

// Log function
function logMessage($message) {
    global $logFile;
    file_put_contents($logFile, date('Y-m-d H:i:s') . ': ' . $message . "\n", FILE_APPEND);
}

// POST /syncing_data
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $_SERVER['REQUEST_URI'] === '/syncing_data') {
    $input = json_decode(file_get_contents('php://input'), true);
    if (!$input || !isset($input['imei'], $input['records'])) {
        logMessage('Invalid syncing_data input');
        http_response_code(400);
        echo json_encode(['error' => 'Invalid input']);
        exit;
    }

    $imei = $input['imei'];
    $records = $input['records'];

    try {
        foreach ($records as $record) {
            $timestamp = $record['timestamp'];
            $latitude = $record['latitude'];
            $longitude = $record['longitude'];
            $altitude = $record['altitude'];
            $speed = $record['speed'];
            $angle = $record['angle'];
            $satellites = $record['satellites'];
            $priority = $record['priority'];

            $stmt = $db->prepare('INSERT INTO gps_data (imei, timestamp, latitude, longitude, altitude, speed, angle, satellites, priority) VALUES (:imei, :timestamp, :latitude, :longitude, :altitude, :speed, :angle, :satellites, :priority)');
            $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
            $stmt->bindValue(':timestamp', $timestamp, SQLITE3_TEXT);
            $stmt->bindValue(':latitude', $latitude, SQLITE3_FLOAT);
            $stmt->bindValue(':longitude', $longitude, SQLITE3_FLOAT);
            $stmt->bindValue(':altitude', $altitude, SQLITE3_INTEGER);
            $stmt->bindValue(':speed', $speed, SQLITE3_INTEGER);
            $stmt->bindValue(':angle', $angle, SQLITE3_INTEGER);
            $stmt->bindValue(':satellites', $satellites, SQLITE3_INTEGER);
            $stmt->bindValue(':priority', $priority, SQLITE3_INTEGER);
            $stmt->execute();

            if (isset($record['io_data'])) {
                foreach ($record['io_data'] as $io) {
                    $stmt = $db->prepare('INSERT INTO io_data (imei, timestamp, io_id, io_value) VALUES (:imei, :timestamp, :io_id, :io_value)');
                    $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
                    $stmt->bindValue(':timestamp', $timestamp, SQLITE3_TEXT);
                    $stmt->bindValue(':io_id', $io['io_id'], SQLITE3_INTEGER);
                    $stmt->bindValue(':io_value', $io['io_value'], SQLITE3_INTEGER);
                    $stmt->execute();
                }
            }
        }
        logMessage("Synced data for IMEI $imei");
        echo json_encode(['status' => 'Data synced']);
    } catch (Exception $e) {
        logMessage("Syncing data failed: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(['error' => 'Server error']);
    }
    $db->close();
    exit;
}

// GET /debug
if ($_SERVER['REQUEST_METHOD'] === 'GET' && $_SERVER['REQUEST_URI'] === '/debug') {
    try {
        $testFile = '/home/yourusername/test.txt';
        file_put_contents($testFile, 'Test file created');
        chmod($testFile, 0666);

        $tables = [];
        $result = $db->query('SELECT name FROM sqlite_master WHERE type="table"');
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            $tables[] = $row['name'];
        }

        $response = [
            'status' => 'Debug successful',
            'log_file_exists' => file_exists($logFile),
            'db_file_exists' => file_exists($dbPath),
            'test_file_exists' => file_exists($testFile),
            'tables' => $tables
        ];
        logMessage("Debug endpoint accessed");
        echo json_encode($response);
    } catch (Exception $e) {
        logMessage("Debug endpoint failed: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(['error' => $e->getMessage()]);
    }
    $db->close();
    exit;
}

// GET /dout1_status/<imei>
if ($_SERVER['REQUEST_METHOD'] === 'GET' && preg_match('#^/dout1_status/(.+)$#', $_SERVER['REQUEST_URI'], $matches)) {
    $imei = $matches[1];
    try {
        $stmt = $db->prepare('SELECT dout1_active, deactivate_time FROM dout1_state WHERE imei = :imei');
        $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
        $result = $stmt->execute();
        $row = $result->fetchArray(SQLITE3_ASSOC);

        if ($row) {
            $response = [
                'imei' => $imei,
                'dout1_active' => (bool)$row['dout1_active'],
                'deactivate_time' => $row['deactivate_time']
            ];
            logMessage("DOUT1 status retrieved for IMEI $imei");
            echo json_encode($response);
        } else {
            logMessage("IMEI $imei not found in dout1_status");
            http_response_code(404);
            echo json_encode(['error' => 'IMEI not found']);
        }
    } catch (Exception $e) {
        logMessage("Error in dout1_status for IMEI $imei: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(['error' => 'Server error']);
    }
    $db->close();
    exit;
}

// GET /power_status/<imei>
if ($_SERVER['REQUEST_METHOD'] === 'GET' && preg_match('#^/power_status/(.+)$#', $_SERVER['REQUEST_URI'], $matches)) {
    $imei = $matches[1];
    try {
        $stmt = $db->prepare('SELECT io_value FROM io_data WHERE imei = :imei AND io_id = 66 ORDER BY timestamp DESC LIMIT 1');
        $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
        $result = $stmt->execute();
        $row = $result->fetchArray(SQLITE3_ASSOC);
        $response = ['power_status' => $row ? (bool)$row['io_value'] : false];
        logMessage("Power status retrieved for IMEI $imei: " . ($row ? $row['io_value'] : 'none'));
        echo json_encode($response);
    } catch (Exception $e) {
        logMessage("Error in power_status for IMEI $imei: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(['error' => 'Server error']);
    }
    $db->close();
    exit;
}

// GET /command_queue/<imei>
if ($_SERVER['REQUEST_METHOD'] === 'GET' && preg_match('#^/command_queue/(.+)$#', $_SERVER['REQUEST_URI'], $matches)) {
    $imei = $matches[1];
    try {
        $stmt = $db->prepare('SELECT id, command FROM command_queue WHERE imei = :imei AND status = :status');
        $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
        $stmt->bindValue(':status', 'pending', SQLITE3_TEXT);
        $result = $stmt->execute();
        $commands = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            $commands[] = ['id' => $row['id'], 'command' => $row['command']];
        }
        logMessage("Retrieved " . count($commands) . " pending commands for IMEI $imei");
        echo json_encode(['commands' => $commands]);
    } catch (Exception $e) {
        logMessage("Error retrieving command queue for IMEI $imei: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(['error' => 'Server error']);
    }
    $db->close();
    exit;
}

// POST /command_queue/update/<id>
if ($_SERVER['REQUEST_METHOD'] === 'POST' && preg_match('#^/command_queue/update/(\d+)$#', $_SERVER['REQUEST_URI'], $matches)) {
    $command_id = $matches[1];
    $input = json_decode(file_get_contents('php://input'), true);
    if (!$input || !isset($input['status'])) {
        logMessage("Invalid input for command_queue/update/$command_id");
        http_response_code(400);
        echo json_encode(['error' => 'Invalid input']);
        exit;
    }

    $status = $input['status'];
    try {
        $stmt = $db->prepare('UPDATE command_queue SET status = :status WHERE id = :id');
        $stmt->bindValue(':status', $status, SQLITE3_TEXT);
        $stmt->bindValue(':id', $command_id, SQLITE3_INTEGER);
        $stmt->execute();
        logMessage("Updated command $command_id to status '$status'");
        echo json_encode(['status' => 'Updated']);
    } catch (Exception $e) {
        logMessage("Error updating command $command_id: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(['error' => 'Server error']);
    }
    $db->close();
    exit;
}

// POST /dout1_control/<imei>
if ($_SERVER['REQUEST_METHOD'] === 'POST' && preg_match('#^/dout1_control/(.+)$#', $_SERVER['REQUEST_URI'], $matches)) {
    $imei = $matches[1];
    $input = json_decode(file_get_contents('php://input'), true);

    if (!$input || !isset($input['activate'])) {
        logMessage("Invalid input for dout1_control, IMEI $imei");
        http_response_code(400);
        echo json_encode(['error' => 'Invalid input']);
        exit;
    }

    $activate = $input['activate'];
    try {
        $stmt = $db->prepare('SELECT dout1_active FROM dout1_state WHERE imei = :imei');
        $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
        $result = $stmt->execute();
        $row = $result->fetchArray(SQLITE3_ASSOC);

        if ($row || !$row) { // Allow initial state creation
            $command = $activate ? 'setdigout 1' : 'setdigout 0';
            $created_at = date('Y-m-d H:i:s');
            $deactivate_time = $activate ? date('Y-m-d H:i:s', strtotime('+1 hour')) : null;
            $stmt = $db->prepare('INSERT OR REPLACE INTO dout1_state (imei, dout1_active, deactivate_time) VALUES (:imei, :active, :deactivate_time)');
            $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
            $stmt->bindValue(':active', $activate ? 1 : 0, SQLITE3_INTEGER);
            $stmt->bindValue(':deactivate_time', $deactivate_time, SQLITE3_TEXT);
            $stmt->execute();

            $stmt = $db->prepare('INSERT INTO command_queue (imei, command, status, created_at) VALUES (:imei, :command, :status, :created_at)');
            $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
            $stmt->bindValue(':command', $command, SQLITE3_TEXT);
            $stmt->bindValue(':status', 'pending', SQLITE3_TEXT);
            $stmt->bindValue(':created_at', $created_at, SQLITE3_TEXT);
            $stmt->execute();

            logMessage("Command queued for IMEI $imei: $command");
            echo json_encode(['command' => $command, 'status' => 'queued']);
        } else {
            logMessage("IMEI $imei not found in dout1_control");
            http_response_code(404);
            echo json_encode(['error' => 'IMEI not found']);
        }
    } catch (Exception $e) {
        logMessage("Error in dout1_control for IMEI $imei: " . $e->getMessage());
        http_response_code(500);
        echo json_encode(['error' => 'Server error']);
    }
    $db->close();
    exit;
}

http_response_code(404);
echo json_encode(['error' => 'Endpoint not found']);
$db->close();
?>