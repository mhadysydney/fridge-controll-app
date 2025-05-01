<template>
  <q-page class="flex flex-center">
    <div class="q-pa-md">
      <h4>DOUT1 Control</h4>
      <q-card class="q-ma-md">
        <q-card-section>
          <div>DOUT1 Status: {{ dout1Active ? 'Active' : 'Inactive' }}</div>
          {{ countdownLabel }}:
          <div v-if="countdown.length > 3">
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
              {{ countdown }}
            </q-circular-progress>
            <!-- {{ countdownLabel }}: {{ countdown }} -->
          </div>
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
import { ref, onMounted, computed, onUnmounted } from 'vue'
import axios from 'axios'
///home/cp1892638p17/virtualenv/virtualenv/pythonVenv/3.12/bin/python /home/cp1892638p17/public_html/iot/grok_fmb_server_v6.py
export default {
  setup() {
    const imei = ref('350317177312182') // Replace with your device's IMEI
    const dout1Active = ref(false)
    const deactivateTime = ref(null)
    const countdown = ref('')
    const countdownLabel = ref('')
    const countdownDuration = ref(0)
    let timer = null
    const countdownProgress = computed(() => {
      return countdownDuration.value - countdown.value
    })
    const fetchStatus = async () => {
      try {
        const response = await axios.get(`https://iot.satgroupe.com/dout1_status/${imei.value}`)
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
        await axios.post(`https://iot.satgroupe.com/dout1_control/${imei.value}`, { activate })
        await fetchStatus()
      } catch (error) {
        console.error('Error controlling DOUT1:', error)
      }
    }

    const updateCountdown = () => {
      console.log('updating countdown: ', deactivateTime.value)

      if (deactivateTime.value) {
        const now = new Date()
        const deactivate = new Date(deactivateTime.value)
        const diff = deactivate - now
        console.log('difff: ', diff)

        if (diff > 0) {
          const seconds = Math.floor(diff / 1000)
          const minutes = Math.floor(seconds / 60)
          const hours = Math.floor(minutes / 60)
          countdown.value = `${hours}:${minutes % 60}:${seconds % 60}`
          countdownLabel.value = dout1Active.value
            ? 'Time until deactivation'
            : 'Time until activation'
        } else {
          countdown.value = ''
          //fetchStatus()
        }
      } else {
        countdown.value = ''
      }
    }

    onMounted(async () => {
      await fetchStatus()

      timer = setInterval(updateCountdown, 10000)
    })

    onUnmounted(() => {
      if (timer) clearInterval(timer)
    })

    return {
      dout1Active,
      countdown,
      countdownLabel,
      toggleDOUT1,
      countdownProgress,
    }
  },
}
</script>
