var byte = 'setdigout 1 4000'
//'8E010000016B412CEE000100000000000000000000000000000000010005000100010100010011001D00010010015E2C880002000B000000003544C87A000E000000001DD7E06A000001'
console.log('byteLen: ', byte.length)

console.log('Generating command')
const codec = '0C',
  type = '05',
  qtity = '01',
  smsCmd = 'setdigout 1 4000'
const cmdEnd = '0D0A'
var cmdLen = smsCmd.length + 2,
  asciihex = '',
  ascii = '',
  packSize = ''
cmdLen = cmdLen.toString(16).toUpperCase()
const msgLen = ('00000000' + cmdLen).slice(-8)
for (let i = 0; i < smsCmd.length; i++) {
  let code = smsCmd.charCodeAt(i)
  ascii += code
  asciihex += code.toString(16)
}

asciihex += cmdEnd
packSize = (asciihex.length + 16) / 2

const dataPackage = codec + qtity + type + msgLen + asciihex + qtity

console.log('Debugging command')

console.log('cmdLen: ', cmdLen)
console.log('msgLen: ', msgLen)
console.log('ascii: ', ascii)
console.log('asciihex: ', asciihex)
console.log('packSize: ', packSize)
console.log('dataPackage: ', dataPackage)
let tmp = '00000000000000180C010500000010676574706172616d2031313130340D0A01000094e3'
console.log('command: ', tmp.replace(/(.{2})/g, '$1 '))
//console.log("genedCommande: ", data.gCmd)
