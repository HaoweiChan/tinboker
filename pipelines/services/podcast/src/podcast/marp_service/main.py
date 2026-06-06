import base64
import logging
import os
import subprocess
import tempfile
import time

from flask import Flask, jsonify, request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route('/upload', methods=['POST'])
def upload_markdown():
    """Legacy endpoint for uploading markdown files"""
    content = request.get_data(as_text=True)
    file_name = str(int(time.time())) + ".md"
    with open(f"data/{file_name}", 'w', encoding='utf-8') as f:
        f.write(content)
    return f'Markdown 文件已保存\n预览链接: http://127.0.0.1:5005/{file_name} \n下载链接: http://127.0.0.1:5005/{file_name}?pptx'


@app.route('/convert', methods=['POST'])
def convert_to_pptx():
    """Convert Marp markdown to PPTX and return base64-encoded file"""
    try:
        # Get markdown content from request
        data = request.get_json()
        if not data or 'markdown' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing markdown field in request body'
            }), 400
        
        markdown_content = data['markdown']
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as md_file:
            md_file.write(markdown_content)
            md_path = md_file.name
        
        timestamp = str(int(time.time()))
        output_filename = f"presentation_{timestamp}.pptx"
        output_path = os.path.join('/tmp', output_filename)
        
        try:
            # Run Marp CLI to convert markdown to PPTX
            logger.info(f"Converting markdown to PPTX: {md_path} -> {output_path}")
            result = subprocess.run(
                ['marp', md_path, '--pptx', '-o', output_path, '--allow-local-files'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"Marp conversion failed: {result.stderr}")
                return jsonify({
                    'success': False,
                    'error': f'Marp conversion failed: {result.stderr}'
                }), 500
            
            # Read the generated PPTX and encode to base64
            with open(output_path, 'rb') as pptx_file:
                pptx_data = pptx_file.read()
                pptx_base64 = base64.b64encode(pptx_data).decode('utf-8')
            
            logger.info(f"Successfully converted to PPTX: {output_filename} ({len(pptx_data)} bytes)")
            
            return jsonify({
                'success': True,
                'pptx_base64': pptx_base64,
                'filename': output_filename,
                'size_bytes': len(pptx_data)
            })
        
        finally:
            # Clean up temporary files
            if os.path.exists(md_path):
                os.unlink(md_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    except subprocess.TimeoutExpired:
        logger.error("Marp conversion timeout")
        return jsonify({
            'success': False,
            'error': 'Conversion timeout (30s)'
        }), 500
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/render-png', methods=['POST'])
def render_to_png():
    """Render Marp markdown to per-slide PNGs; return them base64-encoded in slide order.

    Body: {"markdown": str, "theme_css": str (optional)}. When theme_css is given it is
    loaded via --theme-set (required for custom @size, e.g. the 1080x1080 card theme).
    Returns {"success": true, "images": [base64, ...], "count": N} in slide order.
    """
    import glob

    try:
        data = request.get_json()
        if not data or 'markdown' not in data:
            return jsonify({'success': False, 'error': 'Missing markdown field in request body'}), 400

        with tempfile.TemporaryDirectory() as workdir:
            md_path = os.path.join(workdir, 'deck.md')
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(data['markdown'])

            cmd = ['marp', md_path, '--images', 'png', '--allow-local-files',
                   '-o', os.path.join(workdir, 'slide.png')]
            if data.get('theme_css'):
                theme_path = os.path.join(workdir, 'theme.css')
                with open(theme_path, 'w', encoding='utf-8') as f:
                    f.write(data['theme_css'])
                cmd[1:1] = ['--theme-set', theme_path]

            logger.info("Rendering Marp deck to PNGs")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.error(f"Marp PNG render failed: {result.stderr}")
                return jsonify({'success': False, 'error': f'Marp render failed: {result.stderr}'}), 500

            # Marp emits slide.001.png, slide.002.png, … — collect in numeric order.
            pngs = sorted(glob.glob(os.path.join(workdir, 'slide.*.png')))
            images = []
            for path in pngs:
                with open(path, 'rb') as img:
                    images.append(base64.b64encode(img.read()).decode('utf-8'))

            logger.info(f"Rendered {len(images)} card PNG(s)")
            return jsonify({'success': True, 'images': images, 'count': len(images)})

    except subprocess.TimeoutExpired:
        logger.error("Marp PNG render timeout")
        return jsonify({'success': False, 'error': 'Render timeout (120s)'}), 500
    except Exception as e:
        logger.error(f"Render error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'marp-flask-service'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004)
