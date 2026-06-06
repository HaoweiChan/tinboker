Reference: https://www.assemblyai.com/docs/api-reference/transcripts/submit

## OpenAPI Specification

```yaml
openapi: 3.1.1
info:
  title: Transcribe audio
  version: endpoint_transcripts.submit
paths:
  /v2/transcript:
    post:
      operationId: submit
      summary: Transcribe audio
      description: >
        <Note>To use our EU server for transcription, replace
        `api.assemblyai.com` with `api.eu.assemblyai.com`.</Note>

        Create a transcript from a media file that is accessible via a URL.
      tags:
        - - subpackage_transcripts
      parameters:
        - name: Authorization
          in: header
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Transcript created and queued for processing
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Transcript'
        '400':
          description: Bad request
          content: {}
        '401':
          description: Unauthorized
          content: {}
        '404':
          description: Not found
          content: {}
        '429':
          description: Too many requests
          content: {}
        '500':
          description: An error occurred while processing the request
          content: {}
        '503':
          description: Service unavailable
          content: {}
        '504':
          description: Gateway timeout
          content: {}
      requestBody:
        description: Params to create a transcript
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TranscriptParams'
components:
  schemas:
    TranscriptLanguageCode:
      type: string
      enum:
        - value: en
        - value: en_au
        - value: en_uk
        - value: en_us
        - value: es
        - value: fr
        - value: de
        - value: it
        - value: pt
        - value: nl
        - value: af
        - value: sq
        - value: am
        - value: ar
        - value: hy
        - value: as
        - value: az
        - value: ba
        - value: eu
        - value: be
        - value: bn
        - value: bs
        - value: br
        - value: bg
        - value: my
        - value: ca
        - value: zh
        - value: hr
        - value: cs
        - value: da
        - value: et
        - value: fo
        - value: fi
        - value: gl
        - value: ka
        - value: el
        - value: gu
        - value: ht
        - value: ha
        - value: haw
        - value: he
        - value: hi
        - value: hu
        - value: is
        - value: id
        - value: ja
        - value: jw
        - value: kn
        - value: kk
        - value: km
        - value: ko
        - value: lo
        - value: la
        - value: lv
        - value: ln
        - value: lt
        - value: lb
        - value: mk
        - value: mg
        - value: ms
        - value: ml
        - value: mt
        - value: mi
        - value: mr
        - value: mn
        - value: ne
        - value: 'no'
        - value: nn
        - value: oc
        - value: pa
        - value: ps
        - value: fa
        - value: pl
        - value: ro
        - value: ru
        - value: sa
        - value: sr
        - value: sn
        - value: sd
        - value: si
        - value: sk
        - value: sl
        - value: so
        - value: su
        - value: sw
        - value: sv
        - value: tl
        - value: tg
        - value: ta
        - value: tt
        - value: te
        - value: th
        - value: bo
        - value: tr
        - value: tk
        - value: uk
        - value: ur
        - value: uz
        - value: vi
        - value: cy
        - value: yi
        - value: yo
    TranscriptOptionalParamsLanguageDetectionOptions:
      type: object
      properties:
        expected_languages:
          type: array
          items:
            description: Any type
          description: >-
            List of languages expected in the audio file. Defaults to `["all"]`
            when unspecified.
        fallback_language:
          type: string
          default: auto
          description: >
            If the detected language of the audio file is not in the list of
            expected languages, the `fallback_language` is used. Specify
            `["auto"]` to let our model choose the fallback language from
            `expected_languages` with the highest confidence score.
        code_switching:
          type: boolean
          default: 'false'
          description: |
            Whether code switching should be detected.
        code_switching_confidence_threshold:
          description: >
            The confidence threshold for code switching detection. If the code
            switching confidence is below this threshold, the transcript will be
            processed in the language with the highest
            `language_detection_confidence` score.
    SpeechModel:
      type: string
      enum:
        - description: >-
            The model optimized for accuracy, low latency, ease of use, and
            mutli-language support.
          value: best
        - description: A contextual model optimized for customization.
          value: slam-1
        - description: >-
            The model optimized for accuracy, low latency, ease of use, and
            mutli-language support.
          value: universal
    RedactPiiAudioQuality:
      type: string
      enum:
        - description: MP3 audio format is lower quality and lower size than WAV.
          value: mp3
        - description: >-
            WAV audio format is the highest quality (no compression) and larger
            size than MP3.
          value: wav
    PiiPolicy:
      type: string
      enum:
        - description: >-
            Customer account or membership identification number (e.g., Policy
            No. 10042992, Member ID: HZ-5235-001)
          value: account_number
        - description: Banking information, including account and routing numbers
          value: banking_information
        - description: Blood type (e.g., O-, AB positive)
          value: blood_type
        - description: 'Credit card verification code (e.g., CVV: 080)'
          value: credit_card_cvv
        - description: Expiration date of a credit card
          value: credit_card_expiration
        - description: Credit card number
          value: credit_card_number
        - description: Specific calendar date (e.g., December 18)
          value: date
        - description: >-
            Broader time periods, including date ranges, months, seasons, years,
            and decades (e.g., 2020-2021, 5-9 May, January 1984)
          value: date_interval
        - description: 'Date of birth (e.g., Date of Birth: March 7,1961)'
          value: date_of_birth
        - description: Driver's license number. (e.g., DL# 356933-540)
          value: drivers_license
        - description: >-
            Medications, vitamins, or supplements (e.g., Advil, Acetaminophen,
            Panadol)
          value: drug
        - description: >-
            Periods of time, specified as a number and a unit of time (e.g., 8
            months, 2 years)
          value: duration
        - description: Email address (e.g., support@assemblyai.com)
          value: email_address
        - description: Name of an event or holiday (e.g., Olympics, Yom Kippur)
          value: event
        - description: >-
            Names of computer files, including the extension or filepath (e.g.,
            Taxes/2012/brad-tax-returns.pdf)
          value: filename
        - description: >-
            Terms indicating gender identity or sexual orientation, including
            slang terms (e.g., female, bisexual, trans)
          value: gender_sexuality
        - description: >-
            Healthcare numbers and health plan beneficiary numbers (e.g., Policy
            No.: 5584-486-674-YM)
          value: healthcare_number
        - description: Bodily injury (e.g., I broke my arm, I have a sprained wrist)
          value: injury
        - description: >-
            Internet IP address, including IPv4 and IPv6 formats (e.g.,
            192.168.0.1)
          value: ip_address
        - description: Name of a natural language (e.g., Spanish, French)
          value: language
        - description: >-
            Any Location reference including mailing address, postal code, city,
            state, province, country, or coordinates. (e.g., Lake Victoria, 145
            Windsor St., 90210)
          value: location
        - description: >-
            Terms indicating marital status (e.g., Single, common-law, ex-wife,
            married)
          value: marital_status
        - description: >-
            Name of a medical condition, disease, syndrome, deficit, or disorder
            (e.g., chronic fatigue syndrome, arrhythmia, depression)
          value: medical_condition
        - description: >-
            Medical process, including treatments, procedures, and tests (e.g.,
            heart surgery, CT scan)
          value: medical_process
        - description: Name and/or amount of currency (e.g., 15 pesos, $94.50)
          value: money_amount
        - description: >-
            Terms indicating nationality, ethnicity, or race (e.g., American,
            Asian, Caucasian)
          value: nationality
        - description: >-
            Numerical PII (including alphanumeric strings) that doesn't fall
            under other categories
          value: number_sequence
        - description: Job title or profession (e.g., professor, actors, engineer, CPA)
          value: occupation
        - description: >-
            Name of an organization (e.g., CNN, McDonalds, University of Alaska,
            Northwest General Hospital)
          value: organization
        - description: >-
            Passport numbers, issued by any country (e.g., PA4568332,
            NU3C6L86S12)
          value: passport_number
        - description: >-
            Account passwords, PINs, access keys, or verification answers (e.g.,
            27%alfalfa, temp1234, My mother's maiden name is Smith)
          value: password
        - description: Number associated with an age (e.g., 27, 75)
          value: person_age
        - description: Name of a person (e.g., Bob, Doug Jones, Dr. Kay Martinez, MD)
          value: person_name
        - description: Telephone or fax number
          value: phone_number
        - description: >-
            Distinctive bodily attributes, including terms indicating race
            (e.g., I'm 190cm tall, He belongs to the Black students'
            association)
          value: physical_attribute
        - description: >-
            Terms referring to a political party, movement, or ideology (e.g.,
            Republican, Liberal)
          value: political_affiliation
        - description: Terms indicating religious affiliation (e.g., Hindu, Catholic)
          value: religion
        - description: Medical statistics (e.g., 18%, 18 percent)
          value: statistics
        - description: Expressions indicating clock times (e.g., 19:37:28, 10pm EST)
          value: time
        - description: Internet addresses (e.g., https://www.assemblyai.com/)
          value: url
        - description: Social Security Number or equivalent
          value: us_social_security_number
        - description: Usernames, login names, or handles (e.g., @AssemblyAI)
          value: username
        - description: >-
            Vehicle identification numbers (VINs), vehicle serial numbers, and
            license plate numbers (e.g., 5FNRL38918B111818, BIF7547)
          value: vehicle_id
        - description: Names of Zodiac signs (e.g., Aries, Taurus)
          value: zodiac_sign
    SubstitutionPolicy:
      type: string
      enum:
        - value: entity_name
        - value: hash
    TranscriptOptionalParamsRedactPiiAudioOptions:
      type: object
      properties:
        return_redacted_no_speech_audio:
          type: boolean
          default: false
          description: >-
            By default, audio redaction provides redacted audio URLs only when
            speech is detected. However, if your use-case specifically requires
            redacted audio files even for silent audio files without any
            dialogue, you can opt to receive these URLs by setting this
            parameter to `true`.
    TranscriptOptionalParamsSpeakerOptions:
      type: object
      properties:
        min_speakers_expected:
          type: integer
          default: 1
          description: The minimum number of speakers expected in the audio file.
        max_speakers_expected:
          type: integer
          default: 10
          description: >
            <Warning>Setting this parameter too high may hurt model
            accuracy</Warning>

            The maximum number of speakers expected in the audio file.
    TranscriptCustomSpelling:
      type: object
      properties:
        from:
          type: array
          items:
            type: string
          description: Words or phrases to replace
        to:
          type: string
          description: Word to replace with
      required:
        - from
        - to
    SummaryModel:
      type: string
      enum:
        - value: informative
        - value: conversational
        - value: catchy
    SummaryType:
      type: string
      enum:
        - value: bullets
        - value: bullets_verbose
        - value: gist
        - value: headline
        - value: paragraph
    TranslationRequestBodyTranslation:
      type: object
      properties:
        target_languages:
          type: array
          items:
            type: string
          description: List of target language codes (e.g., `["es", "de"]`)
        formal:
          type: boolean
          default: true
          description: Use formal language style
      required:
        - target_languages
    TranslationRequestBody:
      type: object
      properties:
        translation:
          $ref: '#/components/schemas/TranslationRequestBodyTranslation'
      required:
        - translation
    SpeakerIdentificationRequestBodySpeakerIdentificationSpeakerType:
      type: string
      enum:
        - value: role
        - value: name
    SpeakerIdentificationRequestBodySpeakerIdentification:
      type: object
      properties:
        speaker_type:
          $ref: >-
            #/components/schemas/SpeakerIdentificationRequestBodySpeakerIdentificationSpeakerType
          description: Type of speaker identification
        known_values:
          type: array
          items:
            type: string
          description: >-
            Required if speaker_type is "role". Each value must be 35 characters
            or less.
      required:
        - speaker_type
    SpeakerIdentificationRequestBody:
      type: object
      properties:
        speaker_identification:
          $ref: >-
            #/components/schemas/SpeakerIdentificationRequestBodySpeakerIdentification
      required:
        - speaker_identification
    CustomFormattingRequestBodyCustomFormatting:
      type: object
      properties:
        date:
          type: string
          description: Date format pattern (e.g., `"mm/dd/yyyy"`)
        phone_number:
          type: string
          description: Phone number format pattern (e.g., `"(xxx)xxx-xxxx"`)
        email:
          type: string
          description: Email format pattern (e.g., `"username@domain.com"`)
        format_utterances:
          type: boolean
          default: true
          description: Whether to format utterances
    CustomFormattingRequestBody:
      type: object
      properties:
        custom_formatting:
          $ref: '#/components/schemas/CustomFormattingRequestBodyCustomFormatting'
      required:
        - custom_formatting
    TranscriptOptionalParamsSpeechUnderstandingRequest:
      oneOf:
        - $ref: '#/components/schemas/TranslationRequestBody'
        - $ref: '#/components/schemas/SpeakerIdentificationRequestBody'
        - $ref: '#/components/schemas/CustomFormattingRequestBody'
    TranscriptOptionalParamsSpeechUnderstanding:
      type: object
      properties:
        request:
          $ref: >-
            #/components/schemas/TranscriptOptionalParamsSpeechUnderstandingRequest
      required:
        - request
    TranscriptParams:
      type: object
      properties:
        language_code:
          oneOf:
            - $ref: '#/components/schemas/TranscriptLanguageCode'
            - type: 'null'
          description: >
            The language of your audio file. Possible values are found in
            [Supported
            Languages](https://www.assemblyai.com/docs/concepts/supported-languages).

            The default value is 'en_us'.
        language_codes:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/TranscriptLanguageCode'
          description: >
            The language codes of your audio file. Used for [Code
            switching](/docs/speech-to-text/pre-recorded-audio/code-switching)

            One of the values specified must be `en`.
        language_detection:
          type: boolean
          default: false
          description: >-
            Enable [Automatic language
            detection](https://www.assemblyai.com/docs/models/speech-recognition#automatic-language-detection),
            either true or false.
        language_detection_options:
          $ref: >-
            #/components/schemas/TranscriptOptionalParamsLanguageDetectionOptions
          description: Specify options for Automatic Language Detection.
        language_confidence_threshold:
          type: number
          format: double
          description: >
            The confidence threshold for the automatically detected language.

            An error will be returned if the language confidence is below this
            threshold.

            Defaults to 0.
        speech_model:
          oneOf:
            - $ref: '#/components/schemas/SpeechModel'
            - type: 'null'
          description: >-
            The speech model to use for the transcription. When `null`, the
            `universal` model is used.
        speech_models:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/SpeechModel'
          description: >
            List multiple speech models in priority order, allowing our system
            to automatically route your audio to the best available option.
        punctuate:
          type: boolean
          default: true
          description: Enable Automatic Punctuation, can be true or false
        format_text:
          type: boolean
          default: true
          description: Enable Text Formatting, can be true or false
        disfluencies:
          type: boolean
          default: false
          description: >-
            Transcribe Filler Words, like "umm", in your media file; can be true
            or false
        multichannel:
          type: boolean
          default: false
          description: >-
            Enable
            [Multichannel](https://www.assemblyai.com/docs/models/speech-recognition#multichannel-transcription)
            transcription, can be true or false.
        webhook_url:
          type: string
          format: url
          description: >
            The URL to which we send webhook requests.

            We sends two different types of webhook requests.

            One request when a transcript is completed or failed, and one
            request when the redacted audio is ready if redact_pii_audio is
            enabled.
        webhook_auth_header_name:
          type:
            - string
            - 'null'
          description: >-
            The header name to be sent with the transcript completed or failed
            webhook requests
        webhook_auth_header_value:
          type:
            - string
            - 'null'
          description: >-
            The header value to send back with the transcript completed or
            failed webhook requests for added security
        auto_highlights:
          type: boolean
          default: false
          description: Enable Key Phrases, either true or false
        audio_start_from:
          type: integer
          description: >-
            The point in time, in milliseconds, to begin transcribing in your
            media file
        audio_end_at:
          type: integer
          description: >-
            The point in time, in milliseconds, to stop transcribing in your
            media file
        filter_profanity:
          type: boolean
          default: false
          description: Filter profanity from the transcribed text, can be true or false
        redact_pii:
          type: boolean
          default: false
          description: >-
            Redact PII from the transcribed text using the Redact PII model, can
            be true or false
        redact_pii_audio:
          type: boolean
          default: false
          description: >-
            Generate a copy of the original media file with spoken PII "beeped"
            out, can be true or false. See [PII
            redaction](https://www.assemblyai.com/docs/models/pii-redaction) for
            more details.
        redact_pii_audio_quality:
          $ref: '#/components/schemas/RedactPiiAudioQuality'
          description: >-
            Controls the filetype of the audio created by redact_pii_audio.
            Currently supports mp3 (default) and wav. See [PII
            redaction](https://www.assemblyai.com/docs/models/pii-redaction) for
            more details.
        redact_pii_policies:
          type: array
          items:
            $ref: '#/components/schemas/PiiPolicy'
          description: >-
            The list of PII Redaction policies to enable. See [PII
            redaction](https://www.assemblyai.com/docs/models/pii-redaction) for
            more details.
        redact_pii_sub:
          oneOf:
            - $ref: '#/components/schemas/SubstitutionPolicy'
            - type: 'null'
          description: >-
            The replacement logic for detected PII, can be `entity_type` or
            `hash`. See [PII
            redaction](https://www.assemblyai.com/docs/models/pii-redaction) for
            more details.
        redact_pii_audio_options:
          $ref: '#/components/schemas/TranscriptOptionalParamsRedactPiiAudioOptions'
          description: Specify options for PII redacted audio files.
        speaker_labels:
          type: boolean
          default: false
          description: >-
            Enable [Speaker
            diarization](https://www.assemblyai.com/docs/models/speaker-diarization),
            can be true or false
        speakers_expected:
          type:
            - integer
            - 'null'
          description: >-
            Tells the speaker label model how many speakers it should attempt to
            identify. See [Speaker
            diarization](https://www.assemblyai.com/docs/models/speaker-diarization)
            for more details.
        speaker_options:
          $ref: '#/components/schemas/TranscriptOptionalParamsSpeakerOptions'
          description: Specify options for speaker diarization.
        content_safety:
          type: boolean
          default: false
          description: >-
            Enable [Content
            Moderation](https://www.assemblyai.com/docs/models/content-moderation),
            can be true or false
        content_safety_confidence:
          type: integer
          default: 50
          description: >-
            The confidence threshold for the Content Moderation model. Values
            must be between 25 and 100.
        iab_categories:
          type: boolean
          default: false
          description: >-
            Enable [Topic
            Detection](https://www.assemblyai.com/docs/models/topic-detection),
            can be true or false
        custom_spelling:
          type: array
          items:
            $ref: '#/components/schemas/TranscriptCustomSpelling'
          description: >-
            Customize how words are spelled and formatted using to and from
            values
        keyterms_prompt:
          type: array
          items:
            type: string
          description: >
            Improve accuracy with up to 200 (for Universal) or 1000 (for Slam-1)
            domain-specific words or phrases (maximum 6 words per phrase).
        prompt:
          type: string
          description: >-
            This parameter does not currently have any functionality attached to
            it.
        sentiment_analysis:
          type: boolean
          default: false
          description: >-
            Enable [Sentiment
            Analysis](https://www.assemblyai.com/docs/models/sentiment-analysis),
            can be true or false
        auto_chapters:
          type: boolean
          default: false
          description: >-
            Enable [Auto
            Chapters](https://www.assemblyai.com/docs/models/auto-chapters), can
            be true or false
        entity_detection:
          type: boolean
          default: false
          description: >-
            Enable [Entity
            Detection](https://www.assemblyai.com/docs/models/entity-detection),
            can be true or false
        speech_threshold:
          type:
            - number
            - 'null'
          format: double
          description: |
            Reject audio files that contain less than this fraction of speech.
            Valid values are in the range [0, 1] inclusive.
        summarization:
          type: boolean
          default: false
          description: >-
            Enable
            [Summarization](https://www.assemblyai.com/docs/models/summarization),
            can be true or false
        summary_model:
          $ref: '#/components/schemas/SummaryModel'
          description: The model to summarize the transcript
        summary_type:
          $ref: '#/components/schemas/SummaryType'
          description: The type of summary
        custom_topics:
          type: boolean
          default: false
          description: Enable custom topics, either true or false
        topics:
          type: array
          items:
            type: string
          description: The list of custom topics
        speech_understanding:
          $ref: '#/components/schemas/TranscriptOptionalParamsSpeechUnderstanding'
          description: >-
            Enable speech understanding tasks like translation, speaker
            identification, and custom formatting
        audio_url:
          type: string
          format: url
          description: The URL of the audio or video file to transcribe.
      required:
        - audio_url
    TranscriptStatus:
      type: string
      enum:
        - description: The audio file is in the queue to be processed by the API.
          value: queued
        - description: The audio file is being processed by the API.
          value: processing
        - description: The transcript job has been completed successfully.
          value: completed
        - description: An error occurred while processing the audio file.
          value: error
    TranscriptLanguageDetectionOptions:
      type: object
      properties:
        expected_languages:
          type: array
          items:
            description: Any type
          description: >-
            List of languages expected in the audio file. Defaults to `["all"]`
            when unspecified.
        fallback_language:
          type: string
          default: auto
          description: >
            If the detected language of the audio file is not in the list of
            expected languages, the `fallback_language` is used. Specify
            `["auto"]` to let our model choose the fallback language from
            `expected_languages` with the highest confidence score.
        code_switching:
          type: boolean
          default: 'false'
          description: |
            Whether code switching should be detected.
        code_switching_confidence_threshold:
          description: >
            The confidence threshold for code switching detection. If the code
            switching confidence is below this threshold, the transcript will be
            processed in the language with the highest
            `language_detection_confidence` score.
    TranscriptWord:
      type: object
      properties:
        confidence:
          type: number
          format: double
          description: The confidence score for the transcript of this word
        start:
          type: integer
          description: The starting time, in milliseconds, for the word
        end:
          type: integer
          description: The ending time, in milliseconds, for the word
        text:
          type: string
          description: The text of the word
        channel:
          type:
            - string
            - 'null'
          description: >-
            The channel of the word. The left and right channels are channels 1
            and 2. Additional channels increment the channel number
            sequentially.
        speaker:
          type:
            - string
            - 'null'
          description: >-
            The speaker of the word if [Speaker
            Diarization](https://www.assemblyai.com/docs/models/speaker-diarization)
            is enabled, else null
      required:
        - confidence
        - start
        - end
        - text
        - speaker
    TranscriptUtterance:
      type: object
      properties:
        confidence:
          type: number
          format: double
          description: The confidence score for the transcript of this utterance
        start:
          type: integer
          description: >-
            The starting time, in milliseconds, of the utterance in the audio
            file
        end:
          type: integer
          description: The ending time, in milliseconds, of the utterance in the audio file
        text:
          type: string
          description: The text for this utterance
        words:
          type: array
          items:
            $ref: '#/components/schemas/TranscriptWord'
          description: The words in the utterance.
        channel:
          type:
            - string
            - 'null'
          description: >-
            The channel of this utterance. The left and right channels are
            channels 1 and 2. Additional channels increment the channel number
            sequentially.
        speaker:
          type: string
          description: >-
            The speaker of this utterance, where each speaker is assigned a
            sequential capital letter - e.g. "A" for Speaker A, "B" for Speaker
            B, etc.
      required:
        - confidence
        - start
        - end
        - text
        - words
        - speaker
    AudioIntelligenceModelStatus:
      type: string
      enum:
        - value: success
        - value: unavailable
    Timestamp:
      type: object
      properties:
        start:
          type: integer
          description: The start time in milliseconds
        end:
          type: integer
          description: The end time in milliseconds
      required:
        - start
        - end
    AutoHighlightResult:
      type: object
      properties:
        count:
          type: integer
          description: The total number of times the key phrase appears in the audio file
        rank:
          type: number
          format: double
          description: >-
            The total relevancy to the overall audio file of this key phrase - a
            greater number means more relevant
        text:
          type: string
          description: The text itself of the key phrase
        timestamps:
          type: array
          items:
            $ref: '#/components/schemas/Timestamp'
          description: The timestamp of the of the key phrase
      required:
        - count
        - rank
        - text
        - timestamps
    AutoHighlightsResult:
      type: object
      properties:
        status:
          $ref: '#/components/schemas/AudioIntelligenceModelStatus'
          description: >-
            The status of the Key Phrases model. Either success, or unavailable
            in the rare case that the model failed.
        results:
          type: array
          items:
            $ref: '#/components/schemas/AutoHighlightResult'
          description: A temporally-sequential array of Key Phrases
      required:
        - status
        - results
    ContentSafetyLabel:
      type: object
      properties:
        label:
          type: string
          description: The label of the sensitive topic
        confidence:
          type: number
          format: double
          description: The confidence score for the topic being discussed, from 0 to 1
        severity:
          type: number
          format: double
          description: How severely the topic is discussed in the section, from 0 to 1
      required:
        - label
        - confidence
        - severity
    ContentSafetyLabelResult:
      type: object
      properties:
        text:
          type: string
          description: >-
            The transcript of the section flagged by the Content Moderation
            model
        labels:
          type: array
          items:
            $ref: '#/components/schemas/ContentSafetyLabel'
          description: >-
            An array of safety labels, one per sensitive topic that was detected
            in the section
        sentences_idx_start:
          type: integer
          description: The sentence index at which the section begins
        sentences_idx_end:
          type: integer
          description: The sentence index at which the section ends
        timestamp:
          $ref: '#/components/schemas/Timestamp'
          description: Timestamp information for the section
      required:
        - text
        - labels
        - sentences_idx_start
        - sentences_idx_end
        - timestamp
    SeverityScoreSummary:
      type: object
      properties:
        low:
          type: number
          format: double
        medium:
          type: number
          format: double
        high:
          type: number
          format: double
      required:
        - low
        - medium
        - high
    ContentSafetyLabelsResult:
      type: object
      properties:
        status:
          $ref: '#/components/schemas/AudioIntelligenceModelStatus'
          description: >-
            The status of the Content Moderation model. Either success, or
            unavailable in the rare case that the model failed.
        results:
          type: array
          items:
            $ref: '#/components/schemas/ContentSafetyLabelResult'
          description: An array of results for the Content Moderation model
        summary:
          type: object
          additionalProperties:
            type: number
            format: double
          description: >-
            A summary of the Content Moderation confidence results for the
            entire audio file
        severity_score_summary:
          type: object
          additionalProperties:
            $ref: '#/components/schemas/SeverityScoreSummary'
          description: >-
            A summary of the Content Moderation severity results for the entire
            audio file
      required:
        - status
        - results
        - summary
        - severity_score_summary
    TopicDetectionResultLabelsItems:
      type: object
      properties:
        relevance:
          type: number
          format: double
          description: How relevant the detected topic is of a detected topic
        label:
          type: string
          description: >-
            The IAB taxonomical label for the label of the detected topic, where
            > denotes supertopic/subtopic relationship
      required:
        - relevance
        - label
    TopicDetectionResult:
      type: object
      properties:
        text:
          type: string
          description: The text in the transcript in which a detected topic occurs
        labels:
          type: array
          items:
            $ref: '#/components/schemas/TopicDetectionResultLabelsItems'
          description: An array of detected topics in the text
        timestamp:
          $ref: '#/components/schemas/Timestamp'
      required:
        - text
    TopicDetectionModelResult:
      type: object
      properties:
        status:
          $ref: '#/components/schemas/AudioIntelligenceModelStatus'
          description: >-
            The status of the Topic Detection model. Either success, or
            unavailable in the rare case that the model failed.
        results:
          type: array
          items:
            $ref: '#/components/schemas/TopicDetectionResult'
          description: An array of results for the Topic Detection model
        summary:
          type: object
          additionalProperties:
            type: number
            format: double
          description: The overall relevance of topic to the entire audio file
      required:
        - status
        - results
        - summary
    Chapter:
      type: object
      properties:
        gist:
          type: string
          description: >-
            An ultra-short summary (just a few words) of the content spoken in
            the chapter
        headline:
          type: string
          description: A single sentence summary of the content spoken during the chapter
        summary:
          type: string
          description: A one paragraph summary of the content spoken during the chapter
        start:
          type: integer
          description: The starting time, in milliseconds, for the chapter
        end:
          type: integer
          description: The starting time, in milliseconds, for the chapter
      required:
        - gist
        - headline
        - summary
        - start
        - end
    Sentiment:
      type: string
      enum:
        - value: POSITIVE
        - value: NEUTRAL
        - value: NEGATIVE
    SentimentAnalysisResult:
      type: object
      properties:
        text:
          type: string
          description: The transcript of the sentence
        start:
          type: integer
          description: The starting time, in milliseconds, of the sentence
        end:
          type: integer
          description: The ending time, in milliseconds, of the sentence
        sentiment:
          $ref: '#/components/schemas/Sentiment'
          description: >-
            The detected sentiment for the sentence, one of POSITIVE, NEUTRAL,
            NEGATIVE
        confidence:
          type: number
          format: double
          description: >-
            The confidence score for the detected sentiment of the sentence,
            from 0 to 1
        channel:
          type:
            - string
            - 'null'
          description: >-
            The channel of this utterance. The left and right channels are
            channels 1 and 2. Additional channels increment the channel number
            sequentially.
        speaker:
          type:
            - string
            - 'null'
          description: >-
            The speaker of the sentence if [Speaker
            Diarization](https://www.assemblyai.com/docs/models/speaker-diarization)
            is enabled, else null
      required:
        - text
        - start
        - end
        - sentiment
        - confidence
        - speaker
    EntityType:
      type: string
      enum:
        - description: >-
            Customer account or membership identification number (e.g., Policy
            No. 10042992, Member ID: HZ-5235-001)
          value: account_number
        - description: Banking information, including account and routing numbers
          value: banking_information
        - description: Blood type (e.g., O-, AB positive)
          value: blood_type
        - description: 'Credit card verification code (e.g., CVV: 080)'
          value: credit_card_cvv
        - description: Expiration date of a credit card
          value: credit_card_expiration
        - description: Credit card number
          value: credit_card_number
        - description: Specific calendar date (e.g., December 18)
          value: date
        - description: >-
            Broader time periods, including date ranges, months, seasons, years,
            and decades (e.g., 2020-2021, 5-9 May, January 1984)
          value: date_interval
        - description: 'Date of birth (e.g., Date of Birth: March 7,1961)'
          value: date_of_birth
        - description: Driver's license number. (e.g., DL# 356933-540)
          value: drivers_license
        - description: >-
            Medications, vitamins, or supplements (e.g., Advil, Acetaminophen,
            Panadol)
          value: drug
        - description: >-
            Periods of time, specified as a number and a unit of time (e.g., 8
            months, 2 years)
          value: duration
        - description: Email address (e.g., support@assemblyai.com)
          value: email_address
        - description: Name of an event or holiday (e.g., Olympics, Yom Kippur)
          value: event
        - description: >-
            Names of computer files, including the extension or filepath (e.g.,
            Taxes/2012/brad-tax-returns.pdf)
          value: filename
        - description: >-
            Terms indicating gender identity or sexual orientation, including
            slang terms (e.g., female, bisexual, trans)
          value: gender_sexuality
        - description: >-
            Healthcare numbers and health plan beneficiary numbers (e.g., Policy
            No.: 5584-486-674-YM)
          value: healthcare_number
        - description: Bodily injury (e.g., I broke my arm, I have a sprained wrist)
          value: injury
        - description: >-
            Internet IP address, including IPv4 and IPv6 formats (e.g.,
            192.168.0.1)
          value: ip_address
        - description: Name of a natural language (e.g., Spanish, French)
          value: language
        - description: >-
            Any Location reference including mailing address, postal code, city,
            state, province, country, or coordinates. (e.g., Lake Victoria, 145
            Windsor St., 90210)
          value: location
        - description: >-
            Terms indicating marital status (e.g., Single, common-law, ex-wife,
            married)
          value: marital_status
        - description: >-
            Name of a medical condition, disease, syndrome, deficit, or disorder
            (e.g., chronic fatigue syndrome, arrhythmia, depression)
          value: medical_condition
        - description: >-
            Medical process, including treatments, procedures, and tests (e.g.,
            heart surgery, CT scan)
          value: medical_process
        - description: Name and/or amount of currency (e.g., 15 pesos, $94.50)
          value: money_amount
        - description: >-
            Terms indicating nationality, ethnicity, or race (e.g., American,
            Asian, Caucasian)
          value: nationality
        - description: >-
            Numerical PII (including alphanumeric strings) that doesn't fall
            under other categories
          value: number_sequence
        - description: Job title or profession (e.g., professor, actors, engineer, CPA)
          value: occupation
        - description: >-
            Name of an organization (e.g., CNN, McDonalds, University of Alaska,
            Northwest General Hospital)
          value: organization
        - description: >-
            Passport numbers, issued by any country (e.g., PA4568332,
            NU3C6L86S12)
          value: passport_number
        - description: >-
            Account passwords, PINs, access keys, or verification answers (e.g.,
            27%alfalfa, temp1234, My mother's maiden name is Smith)
          value: password
        - description: Number associated with an age (e.g., 27, 75)
          value: person_age
        - description: Name of a person (e.g., Bob, Doug Jones, Dr. Kay Martinez, MD)
          value: person_name
        - description: Telephone or fax number
          value: phone_number
        - description: >-
            Distinctive bodily attributes, including terms indicating race
            (e.g., I'm 190cm tall, He belongs to the Black students'
            association)
          value: physical_attribute
        - description: >-
            Terms referring to a political party, movement, or ideology (e.g.,
            Republican, Liberal)
          value: political_affiliation
        - description: Terms indicating religious affiliation (e.g., Hindu, Catholic)
          value: religion
        - description: Medical statistics (e.g., 18%, 18 percent)
          value: statistics
        - description: Expressions indicating clock times (e.g., 19:37:28, 10pm EST)
          value: time
        - description: Internet addresses (e.g., https://www.assemblyai.com/)
          value: url
        - description: Social Security Number or equivalent
          value: us_social_security_number
        - description: Usernames, login names, or handles (e.g., @AssemblyAI)
          value: username
        - description: >-
            Vehicle identification numbers (VINs), vehicle serial numbers, and
            license plate numbers (e.g., 5FNRL38918B111818, BIF7547)
          value: vehicle_id
        - description: Names of Zodiac signs (e.g., Aries, Taurus)
          value: zodiac_sign
    Entity:
      type: object
      properties:
        entity_type:
          $ref: '#/components/schemas/EntityType'
          description: The type of entity for the detected entity
        text:
          type: string
          description: The text for the detected entity
        start:
          type: integer
          description: >-
            The starting time, in milliseconds, at which the detected entity
            appears in the audio file
        end:
          type: integer
          description: >-
            The ending time, in milliseconds, for the detected entity in the
            audio file
      required:
        - entity_type
        - text
        - start
        - end
    TranscriptSpeechUnderstandingRequest:
      oneOf:
        - $ref: '#/components/schemas/TranslationRequestBody'
        - $ref: '#/components/schemas/SpeakerIdentificationRequestBody'
        - $ref: '#/components/schemas/CustomFormattingRequestBody'
    TranslationResponseTranslation:
      type: object
      properties:
        status:
          type: string
    TranslationResponse:
      type: object
      properties:
        translation:
          $ref: '#/components/schemas/TranslationResponseTranslation'
    SpeakerIdentificationResponseSpeakerIdentification:
      type: object
      properties:
        status:
          type: string
    SpeakerIdentificationResponse:
      type: object
      properties:
        speaker_identification:
          $ref: >-
            #/components/schemas/SpeakerIdentificationResponseSpeakerIdentification
    CustomFormattingResponseCustomFormatting:
      type: object
      properties:
        mapping:
          type: object
          additionalProperties:
            type: string
        formatted_text:
          type: string
    CustomFormattingResponse:
      type: object
      properties:
        custom_formatting:
          $ref: '#/components/schemas/CustomFormattingResponseCustomFormatting'
    TranscriptSpeechUnderstandingResponse:
      oneOf:
        - $ref: '#/components/schemas/TranslationResponse'
        - $ref: '#/components/schemas/SpeakerIdentificationResponse'
        - $ref: '#/components/schemas/CustomFormattingResponse'
    TranscriptSpeechUnderstanding:
      type: object
      properties:
        request:
          $ref: '#/components/schemas/TranscriptSpeechUnderstandingRequest'
        response:
          $ref: '#/components/schemas/TranscriptSpeechUnderstandingResponse'
      required:
        - request
    TranscriptTranslatedTexts:
      type: object
      properties:
        language_code:
          type: string
          description: Translated text for this language code
    Transcript:
      type: object
      properties:
        id:
          type: string
          format: uuid
          description: The unique identifier of your transcript
        audio_url:
          type: string
          format: url
          description: The URL of the media that was transcribed
        status:
          $ref: '#/components/schemas/TranscriptStatus'
          description: >-
            The status of your transcript. Possible values are queued,
            processing, completed, or error.
        language_code:
          $ref: '#/components/schemas/TranscriptLanguageCode'
          description: >
            The language of your audio file.

            Possible values are found in [Supported
            Languages](https://www.assemblyai.com/docs/concepts/supported-languages).

            The default value is 'en_us'.
        language_codes:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/TranscriptLanguageCode'
          description: >
            The language codes of your audio file. Used for [Code
            switching](/docs/speech-to-text/pre-recorded-audio/code-switching)

            One of the values specified must be `en`.
        language_detection:
          type:
            - boolean
            - 'null'
          description: >-
            Whether [Automatic language
            detection](/docs/pre-recorded-audio/automatic-language-detection) is
            enabled, either true or false
        language_detection_options:
          $ref: '#/components/schemas/TranscriptLanguageDetectionOptions'
          description: Specify options for Automatic Language Detection.
        language_confidence_threshold:
          type:
            - number
            - 'null'
          format: double
          description: >
            The confidence threshold for the automatically detected language.

            An error will be returned if the language confidence is below this
            threshold.
        language_confidence:
          type:
            - number
            - 'null'
          format: double
          description: >-
            The confidence score for the detected language, between 0.0 (low
            confidence) and 1.0 (high confidence)
        speech_model:
          oneOf:
            - $ref: '#/components/schemas/SpeechModel'
            - type: 'null'
          description: >-
            The speech model used for the transcription. When `null`, the
            `universal` model is used.
        speech_models:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/SpeechModel'
          description: >
            List multiple speech models in priority order, allowing our system
            to automatically route your audio to the best available option.
        speech_model_used:
          $ref: '#/components/schemas/SpeechModel'
          description: The speech model that was actually used for the transcription.
        text:
          type:
            - string
            - 'null'
          description: The textual transcript of your media file
        words:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/TranscriptWord'
          description: >
            An array of temporally-sequential word objects, one for each word in
            the transcript.

            See [Speech
            recognition](https://www.assemblyai.com/docs/models/speech-recognition)
            for more information.
        utterances:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/TranscriptUtterance'
          description: >
            When multichannel or speaker_labels is enabled, a list of
            turn-by-turn utterance objects.

            See [Speaker
            diarization](https://www.assemblyai.com/docs/speech-to-text/speaker-diarization)
            and [Multichannel
            transcription](https://www.assemblyai.com/docs/speech-to-text/speech-recognition#multichannel-transcription)
            for more information.
        confidence:
          type:
            - number
            - 'null'
          format: double
          description: >-
            The confidence score for the transcript, between 0.0 (low
            confidence) and 1.0 (high confidence)
        audio_duration:
          type:
            - integer
            - 'null'
          description: The duration of this transcript object's media file, in seconds
        punctuate:
          type:
            - boolean
            - 'null'
          description: Whether Automatic Punctuation is enabled, either true or false
        format_text:
          type:
            - boolean
            - 'null'
          description: Whether Text Formatting is enabled, either true or false
        disfluencies:
          type:
            - boolean
            - 'null'
          description: >-
            Transcribe Filler Words, like "umm", in your media file; can be true
            or false
        multichannel:
          type:
            - boolean
            - 'null'
          description: >-
            Whether [Multichannel
            transcription](https://www.assemblyai.com/docs/models/speech-recognition#multichannel-transcription)
            was enabled in the transcription request, either true or false
        audio_channels:
          type: integer
          description: >-
            The number of audio channels in the audio file. This is only present
            when multichannel is enabled.
        webhook_url:
          type:
            - string
            - 'null'
          format: url
          description: >
            The URL to which we send webhook requests.

            We sends two different types of webhook requests.

            One request when a transcript is completed or failed, and one
            request when the redacted audio is ready if redact_pii_audio is
            enabled.
        webhook_status_code:
          type:
            - integer
            - 'null'
          description: >-
            The status code we received from your server when delivering the
            transcript completed or failed webhook request, if a webhook URL was
            provided
        webhook_auth:
          type: boolean
          description: Whether webhook authentication details were provided
        webhook_auth_header_name:
          type:
            - string
            - 'null'
          description: >-
            The header name to be sent with the transcript completed or failed
            webhook requests
        speed_boost:
          type:
            - boolean
            - 'null'
          description: Whether speed boost is enabled
        auto_highlights:
          type: boolean
          description: Whether Key Phrases is enabled, either true or false
        auto_highlights_result:
          oneOf:
            - $ref: '#/components/schemas/AutoHighlightsResult'
            - type: 'null'
          description: >
            An array of results for the Key Phrases model, if it is enabled.

            See [Key
            Phrases](https://www.assemblyai.com/docs/models/key-phrases) for
            more information.
        audio_start_from:
          type:
            - integer
            - 'null'
          description: >-
            The point in time, in milliseconds, in the file at which the
            transcription was started
        audio_end_at:
          type:
            - integer
            - 'null'
          description: >-
            The point in time, in milliseconds, in the file at which the
            transcription was terminated
        filter_profanity:
          type:
            - boolean
            - 'null'
          description: >-
            Whether [Profanity
            Filtering](https://www.assemblyai.com/docs/models/speech-recognition#profanity-filtering)
            is enabled, either true or false
        redact_pii:
          type: boolean
          description: >-
            Whether [PII
            Redaction](https://www.assemblyai.com/docs/models/pii-redaction) is
            enabled, either true or false
        redact_pii_audio:
          type:
            - boolean
            - 'null'
          description: >
            Whether a redacted version of the audio file was generated,

            either true or false. See [PII
            redaction](https://www.assemblyai.com/docs/models/pii-redaction) for
            more information.
        redact_pii_audio_quality:
          oneOf:
            - $ref: '#/components/schemas/RedactPiiAudioQuality'
            - type: 'null'
          description: >
            The audio quality of the PII-redacted audio file, if
            redact_pii_audio is enabled.

            See [PII
            redaction](https://www.assemblyai.com/docs/models/pii-redaction) for
            more information.
        redact_pii_policies:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/PiiPolicy'
          description: >
            The list of PII Redaction policies that were enabled, if PII
            Redaction is enabled.

            See [PII
            redaction](https://www.assemblyai.com/docs/models/pii-redaction) for
            more information.
        redact_pii_sub:
          $ref: '#/components/schemas/SubstitutionPolicy'
          description: >-
            The replacement logic for detected PII, can be `entity_type` or
            `hash`. See [PII
            redaction](https://www.assemblyai.com/docs/models/pii-redaction) for
            more details.
        speaker_labels:
          type:
            - boolean
            - 'null'
          description: >-
            Whether [Speaker
            diarization](https://www.assemblyai.com/docs/models/speaker-diarization)
            is enabled, can be true or false
        speakers_expected:
          type:
            - integer
            - 'null'
          description: >-
            Tell the speaker label model how many speakers it should attempt to
            identify. See [Speaker
            diarization](https://www.assemblyai.com/docs/models/speaker-diarization)
            for more details.
        content_safety:
          type:
            - boolean
            - 'null'
          description: >-
            Whether [Content
            Moderation](https://www.assemblyai.com/docs/models/content-moderation)
            is enabled, can be true or false
        content_safety_labels:
          oneOf:
            - $ref: '#/components/schemas/ContentSafetyLabelsResult'
            - type: 'null'
          description: >
            An array of results for the Content Moderation model, if it is
            enabled.

            See [Content
            moderation](https://www.assemblyai.com/docs/models/content-moderation)
            for more information.
        iab_categories:
          type:
            - boolean
            - 'null'
          description: >-
            Whether [Topic
            Detection](https://www.assemblyai.com/docs/models/topic-detection)
            is enabled, can be true or false
        iab_categories_result:
          oneOf:
            - $ref: '#/components/schemas/TopicDetectionModelResult'
            - type: 'null'
          description: >
            The result of the Topic Detection model, if it is enabled.

            See [Topic
            Detection](https://www.assemblyai.com/docs/models/topic-detection)
            for more information.
        custom_spelling:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/TranscriptCustomSpelling'
          description: >-
            Customize how words are spelled and formatted using to and from
            values
        keyterms_prompt:
          type: array
          items:
            type: string
          description: >
            Improve accuracy with up to 200 (for Universal) or 1000 (for Slam-1)
            domain-specific words or phrases (maximum 6 words per phrase).
        prompt:
          type: string
          description: >-
            This parameter does not currently have any functionality attached to
            it.
        auto_chapters:
          type:
            - boolean
            - 'null'
          description: >-
            Whether [Auto
            Chapters](https://www.assemblyai.com/docs/models/auto-chapters) is
            enabled, can be true or false
        chapters:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/Chapter'
          description: An array of temporally sequential chapters for the audio file
        summarization:
          type: boolean
          description: >-
            Whether
            [Summarization](https://www.assemblyai.com/docs/models/summarization)
            is enabled, either true or false
        summary_type:
          type:
            - string
            - 'null'
          description: >-
            The type of summary generated, if
            [Summarization](https://www.assemblyai.com/docs/models/summarization)
            is enabled
        summary_model:
          type:
            - string
            - 'null'
          description: >
            The Summarization model used to generate the summary,

            if
            [Summarization](https://www.assemblyai.com/docs/models/summarization)
            is enabled
        summary:
          type:
            - string
            - 'null'
          description: >-
            The generated summary of the media file, if
            [Summarization](https://www.assemblyai.com/docs/models/summarization)
            is enabled
        custom_topics:
          type:
            - boolean
            - 'null'
          description: Whether custom topics is enabled, either true or false
        topics:
          type: array
          items:
            type: string
          description: The list of custom topics provided if custom topics is enabled
        sentiment_analysis:
          type:
            - boolean
            - 'null'
          description: >-
            Whether [Sentiment
            Analysis](https://www.assemblyai.com/docs/models/sentiment-analysis)
            is enabled, can be true or false
        sentiment_analysis_results:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/SentimentAnalysisResult'
          description: >
            An array of results for the Sentiment Analysis model, if it is
            enabled.

            See [Sentiment
            Analysis](https://www.assemblyai.com/docs/models/sentiment-analysis)
            for more information.
        entity_detection:
          type:
            - boolean
            - 'null'
          description: >-
            Whether [Entity
            Detection](https://www.assemblyai.com/docs/models/entity-detection)
            is enabled, can be true or false
        entities:
          type:
            - array
            - 'null'
          items:
            $ref: '#/components/schemas/Entity'
          description: >
            An array of results for the Entity Detection model, if it is
            enabled.

            See [Entity
            detection](https://www.assemblyai.com/docs/models/entity-detection)
            for more information.
        speech_threshold:
          type:
            - number
            - 'null'
          format: double
          description: >
            Defaults to null. Reject audio files that contain less than this
            fraction of speech.

            Valid values are in the range [0, 1] inclusive.
        throttled:
          type:
            - boolean
            - 'null'
          description: >-
            True while a request is throttled and false when a request is no
            longer throttled
        error:
          type: string
          description: Error message of why the transcript failed
        language_model:
          type: string
          description: The language model that was used for the transcript
        acoustic_model:
          type: string
          description: The acoustic model that was used for the transcript
        speech_understanding:
          $ref: '#/components/schemas/TranscriptSpeechUnderstanding'
          description: >-
            Enable speech understanding tasks like translation, speaker
            identification, and custom formatting
        translated_texts:
          $ref: '#/components/schemas/TranscriptTranslatedTexts'
          description: Translated text keyed by language code
      required:
        - id
        - audio_url
        - status
        - language_confidence_threshold
        - language_confidence
        - speech_model
        - webhook_auth
        - auto_highlights
        - redact_pii
        - summarization
        - language_model
        - acoustic_model

```