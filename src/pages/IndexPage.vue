<template>
  <q-page class="q-pa-md">
    <!-- Header with Freezer Image -->
    <div class="q-mb-lg text-center">
      <img
        src="https://images.unsplash.com/photo-1622138812814-5b30c037f127?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80"
        alt="American Freezer"
        class="freezer-image"
      />
      <h4 class="q-mt-md text-h5 text-weight-bold">Smart Fridge Control</h4>
    </div>

    <!-- Status Cards -->
    <div class="q-gutter-md row justify-center">
      <!-- Fridge Status -->
      <q-card class="status-card col-5">
        <q-card-section class="text-center">
          <q-icon
            :name="fridgeStatus ? 'ac_unit' : 'power_off'"
            size="lg"
            :color="fridgeStatus ? 'green' : 'grey'"
          />
          <div class="q-mt-sm text-subtitle1">Fridge {{ fridgeStatus ? 'On' : 'Off' }}</div>
        </q-card-section>
      </q-card>

      <!-- Power Source -->
      <q-card class="status-card col-5">
        <q-card-section class="text-center">
          <q-icon
            :name="powerStatus ? 'plug_circle' : 'power_off'"
            size="lg"
            :color="powerStatus ? 'green' : 'red'"
          />
          <div class="q-mt-sm text-subtitle1">
            {{ powerStatus ? 'Plugged In' : 'Unplugged' }}
          </div>
        </q-card-section>
      </q-card>
    </div>

    <!-- Circular Progress for Defrost Countdown -->
    <div class="q-mt-lg text-center">
      <q-circular-progress
        show-value
        :value="progressValue"
        size="150px"
        :thickness="0.2"
        color="primary"
        track-color="grey-3"
        class="q-ma-md"
      >
        <div class="text-body1">
          {{ remainingTime }}
        </div>
      </q-circular-progress>
      <div class="q-mt-sm text-subtitle1">
        {{ fridgeStatus ? 'Time until Defrost Off' : 'Time until Defrost On' }}
      </div>
    </div>

    <!-- Control Buttons -->
    <div class="q-mt-lg text-center">
      <q-btn
        :label="fridgeStatus ? 'Turn Off Defrost' : 'Turn On Defrost'"
        :color="fridgeStatus ? 'negative' : 'primary'"
        :loading="loading"
        @click="toggleDefrost"
        class="q-px-lg"
      />
    </div>
  </q-page>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

export default {
  name: 'IndexPage',
  setup() {
    const apiBaseUrl = 'https://iot.satgroupe.com' // Adjust to your cPanel subdomain or IP
    const imei = '350317177312182' // Replace with your FMB920 IMEI
    const fridgeStatus = ref(false)
    const powerStatus = ref(false)
    const deactivateTime = ref(null)
    const loading = ref(false)

    // Circular progress (0-100%)
    const progressValue = computed(() => {
      if (!deactivateTime.value) return 0
      const now = new Date()
      const end = new Date(deactivateTime.value)
      const total = 60 * 60 * 1000 // 1 hour in ms
      const remaining = Math.max(0, end - now)
      return (remaining / total) * 100
    })

    // Format remaining time (MM:SS)
    const remainingTime = computed(() => {
      if (!deactivateTime.value) return 'N/A'
      const now = new Date()
      const end = new Date(deactivateTime.value)
      const diff = Math.max(0, end - now) / 1000 // Seconds
      const minutes = Math.floor(diff / 60)
      const seconds = Math.floor(diff % 60)
      return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
    })

    // Fetch status every 10 seconds
    const fetchStatus = async () => {
      try {
        // Fetch fridge status
        const response = await axios.get(`${apiBaseUrl}/dout1_status/${imei}`)
        fridgeStatus.value = response.data.dout1_active
        deactivateTime.value = response.data.deactivate_time

        // Fetch power status (IO ID 66)
        const powerResponse = await axios.get(`${apiBaseUrl}/power_status/${imei}`)
        powerStatus.value = powerResponse.data.power_status
      } catch (error) {
        console.error('Error fetching status:', error)
      }
    }

    // Toggle defrost
    const toggleDefrost = async () => {
      loading.value = true
      try {
        await axios.post(`${apiBaseUrl}/dout1_control/${imei}`, {
          activate: !fridgeStatus.value,
        })
        await fetchStatus()
      } catch (error) {
        console.error('Error toggling defrost:', error)
      } finally {
        loading.value = false
      }
    }

    // Poll every 10 seconds
    let intervalId
    onMounted(() => {
      fetchStatus()
      intervalId = setInterval(fetchStatus, 10000) // 10-second interval
    })

    onUnmounted(() => {
      clearInterval(intervalId)
    })

    return {
      fridgeStatus,
      powerStatus,
      progressValue,
      remainingTime,
      loading,
      toggleDefrost,
    }
  },
}
</script>

<style scoped>
.freezer-image {
  max-width: 300px;
  border-radius: 10px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

.status-card {
  min-width: 150px;
  text-align: center;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.q-page {
  background: linear-gradient(to bottom, #f0f4f8, #ffffff);
}
</style>
