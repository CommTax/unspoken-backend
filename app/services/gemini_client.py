// Test the full flow with longer timeout
async function testFullFlow() {
  const testText = "I am a senior program manager currently working with Wellness Limited and managing Food Project two of the matter to consumer for this and two of the mark for internal stakeholders which is our posting the one on the consumers side are distillation OPD services in India and they are launched occurs 4gbm channel the second project is on IBS which is also against to GTM";
  
  console.log('🚀 Testing with 45s timeout...');
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    console.log('⏰ Aborting after 45s');
    controller.abort();
  }, 45000);
  
  const startTime = Date.now();
  
  try {
    const response = await fetch('https://unspoken-backend-yvbi.onrender.com/api/communication/analyze/premium', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: testText,
        mode: 'voice',
        question_type: 'intro'
      }),
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    const endTime = Date.now();
    console.log(`⏱️ Total time: ${(endTime - startTime) / 1000}s`);
    
    if (!response.ok) {
      console.error('❌ HTTP Error:', response.status);
      return;
    }
    
    const data = await response.json();
    console.log('✅ Response:', data);
    console.log('📊 Impact Score:', data?.metrics?.impact);
    console.log('🧠 Pattern:', data?.diagnosis?.pattern_name);
    console.log('💡 What Got Lost:', data?.gap?.what_got_lost);
    console.log('✍️ Executive Version:', data?.before_after_rewrite?.executive_version);
    
    return data;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      console.error('❌ Request aborted (timeout)');
    } else {
      console.error('❌ Error:', error);
    }
  }
}

testFullFlow();
