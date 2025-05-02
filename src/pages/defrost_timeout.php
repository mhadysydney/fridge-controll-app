<?php
$dbPath = '/home/yourusername/fmb_data.db';
$logFile = '/home/yourusername/fmb_server.log';
$imei = 'YOUR_IMEI'; // Replace with your FMB920 IMEI

try {
    $db = new SQLite3($dbPath);
    $stmt = $db->prepare('SELECT dout1_active, deactivate_time FROM dout1_state WHERE imei = :imei');
    $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
    $result = $stmt->execute();
    $row = $result->fetchArray(SQLITE3_ASSOC);

    if ($row && $row['dout1_active']) {
        $deactivate_time = strtotime($row['deactivate_time']);
        $now = time();
        if ($deactivate_time < $now) {
            $command = 'setdigout 0';
            $created_at = date('Y-m-d H:i:s');
            $stmt = $db->prepare('INSERT INTO command_queue (imei, command, status, created_at) VALUES (:imei, :command, :status, :created_at)');
            $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
            $stmt->bindValue(':command', $command, SQLITE3_TEXT);
            $stmt->bindValue(':status', 'pending', SQLITE3_TEXT);
            $stmt->bindValue(':created_at', $created_at, SQLITE3_TEXT);
            $stmt->execute();

           /*  $stmt = $db->prepare('UPDATE dout1_state SET dout1_active = 0, deactivate_time = NULL WHERE imei = :imei');
            $stmt->bindValue(':imei', $imei, SQLITE3_TEXT);
            $stmt->execute(); */

            file_put_contents($logFile, date('Y-m-d H:i:s') . ": Cron forced defrost off for IMEI $imei\n", FILE_APPEND);
        }
    }
    $db->close();
} catch (Exception $e) {
    file_put_contents($logFile, date('Y-m-d H:i:s') . ': Cron error: ' . $e->getMessage() . "\n", FILE_APPEND);
}
?>