<template>
  <q-page padding>
    <div class="q-pa-md">
      <h5>DOUT1 Control</h5>
      <q-input
        v-model="imei"
        label="Enter IMEI"
        filled
        class="q-mb-md"
        :rules="[(val) => !!val || 'IMEI is required']"
      />
      <q-btn
        :label="status ? 'Deactivate DOUT1' : 'Activate DOUT1'"
        :color="status ? 'negative' : 'primary'"
        :loading="loading"
        :disable="!imei"
        @click="toggleDout1"
        class="q-mb-md full-width"
      />
      <div v-if="error" class="text-negative q-mb-md">
        {{ error }}
      </div>
      <div v-if="status !== null" class="q-mb-md">
        <p>
          DOUT1 Status: <strong>{{ status ? 'Active' : 'Inactive' }}</strong>
        </p>
        <div v-if="countdown > 0">
          <q-circular-progress
            show-value
            font-size="14px"
            :value="countdownProgress"
            size="100px"
            :thickness="0.2"
            color="primary"
            track-color="grey-3"
            :min="0"
            :max="countdownDuration"
            class="q-ma-md"
          >
            {{ Math.ceil(countdown / 1000) }}s
          </q-circular-progress>
          <p>Time until deactivation: {{ Math.ceil(countdown / 1000) }} seconds</p>
        </div>
        <div v-else-if="status">
          <p>No deactivation scheduled</p>
        </div>
      </div>
    </div>
  </q-page>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

export default {
  name: 'IndexPage',
  setup() {
    const apiBaseUrl = 'https://iot.satgroupe.com' // Replace with your cPanel domain
    const imei = ref('350317177312182') // Replace with a default IMEI or keep as user input
    const status = ref(null) // DOUT1 active status (true/false)
    const deactivateTime = ref(null) // Deactivation timestamp
    const countdown = ref(0) // Countdown in milliseconds
    const countdownDuration = ref(0) // Total countdown duration in milliseconds
    const loading = ref(false)
    const error = ref(null)
    let countdownInterval = null

    // Compute countdown progress for Q-Circular-Progress
    const countdownProgress = computed(() => {
      return countdownDuration.value - countdown.value
    })

    // Fetch DOUT1 status
    const fetchStatus = async () => {
      if (!imei.value) return
      loading.value = true
      error.value = null
      try {
        const response = await axios.get(`${apiBaseUrl}/dout1_status/${imei.value}`)
        status.value = response.data.dout1_active
        console.log('status: ', status.value, '\ndeactivateTime.value: ', deactivateTime.value)

        deactivateTime.value = response.data.deactivate_time
        if (deactivateTime.value) {
          startCountdown()
        } else {
          stopCountdown()
          countdown.value = 0
        }
      } catch (err) {
        error.value = err.response?.data?.error || 'Failed to fetch status'
        status.value = null
        stopCountdown()
      } finally {
        loading.value = false
      }
    }

    // Toggle DOUT1 (activate/deactivate)
    const toggleDout1 = async () => {
      if (!imei.value) return
      loading.value = true
      error.value = null
      try {
        const response = await axios.post(`${apiBaseUrl}/dout1_control/${imei.value}`, {
          activate: !status.value,
        })
        if (response.data.status === 'queued') {
          await fetchStatus() // Refresh status after command
        }
      } catch (err) {
        error.value = err.response?.data?.error || 'Failed to control DOUT1'
      } finally {
        loading.value = false
      }
    }

    // Start countdown based on deactivate_time
    const startCountdown = () => {
      stopCountdown() // Clear existing interval
      const deactivateDate = new Date(deactivateTime.value)
      const now = new Date()
      countdownDuration.value = Math.max(0, deactivateDate - now)
      countdown.value = countdownDuration.value

      if (countdown.value > 0) {
        countdownInterval = setInterval(() => {
          countdown.value -= 1000
          if (countdown.value <= 0) {
            stopCountdown()
            fetchStatus() // Refresh status when countdown ends
          }
        }, 1000)
      }
    }

    // Stop countdown
    const stopCountdown = () => {
      if (countdownInterval) {
        clearInterval(countdownInterval)
        countdownInterval = null
      }
    }

    // Fetch status on mount
    onMounted(() => {
      if (imei.value) {
        fetchStatus()
      }
    })

    // Clean up interval on unmount
    onUnmounted(() => {
      stopCountdown()
    })

    return {
      imei,
      status,
      countdown,
      countdownDuration,
      countdownProgress,
      loading,
      error,
      toggleDout1,
    }
  },
}
</script>

<style scoped>
.q-page {
  display: flex;
  justify-content: center;
}
.q-pa-md {
  max-width: 500px;
  width: 100%;
}
</style>
