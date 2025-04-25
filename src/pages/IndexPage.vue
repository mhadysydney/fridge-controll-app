<template>
  <q-page class="flex flex-center">
    <div class="q-pa-md">
      <h4>DOUT1 Control</h4>
      <q-card class="q-ma-md">
        <q-card-section>
          <div>DOUT1 Status: {{ dout1Active ? 'Active' : 'Inactive' }}</div>
          <div v-if="countdown">{{ countdownLabel }}: {{ countdown }}</div>
          <div v-else>No scheduled activation/deactivation</div>
        </q-card-section>
        <q-card-actions>
          <q-btn
            :color="dout1Active ? 'negative' : 'primary'"
            :label="dout1Active ? 'Deactivate DOUT1' : 'Activate DOUT1'"
            @click="toggleDOUT1"
          />
        </q-card-actions>
      </q-card>
    </div>
  </q-page>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

export default {
  setup() {
    const imei = ref('350317177312182') // Replace with your device's IMEI
    const dout1Active = ref(false)
    const deactivateTime = ref(null)
    const countdown = ref('')
    const countdownLabel = ref('')
    let timer = null

    const fetchStatus = async () => {
      try {
        const response = await axios.get(`https://satgroupe.com:50121/dout1_status/${imei.value}`)
        dout1Active.value = response.data.dout1_active
        deactivateTime.value = response.data.deactivate_time
        updateCountdown()
      } catch (error) {
        console.error('Error fetching status:', error)
      }
    }

    const toggleDOUT1 = async () => {
      try {
        const activate = !dout1Active.value
        await axios.post(`http://YOUR_SERVER_IP:5000/dout1_control/${imei.value}`, { activate })
        await fetchStatus()
      } catch (error) {
        console.error('Error controlling DOUT1:', error)
      }
    }

    const updateCountdown = () => {
      if (deactivateTime.value) {
        const now = new Date()
        const deactivate = new Date(deactivateTime.value)
        const diff = deactivate - now
        if (diff > 0) {
          const seconds = Math.floor(diff / 1000)
          const minutes = Math.floor(seconds / 60)
          const hours = Math.floor(minutes / 60)
          countdown.value = `${hours}h ${minutes % 60}m ${seconds % 60}s`
          countdownLabel.value = dout1Active.value
            ? 'Time until deactivation'
            : 'Time until activation'
        } else {
          countdown.value = ''
          fetchStatus()
        }
      } else {
        countdown.value = ''
      }
    }

    onMounted(() => {
      fetchStatus()
      timer = setInterval(updateCountdown, 1000)
    })

    onUnmounted(() => {
      if (timer) clearInterval(timer)
    })

    return {
      dout1Active,
      countdown,
      countdownLabel,
      toggleDOUT1,
    }
  },
}
</script>
